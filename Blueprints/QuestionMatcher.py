from flask import Blueprint, request, jsonify
from typing import List, Dict, Set, Optional
from pyparsing import Iterable
from firebase.firebase import db
import random
import re

question_match = Blueprint("question_match", __name__)
STOPWORDS = {"the", "and", "or", "of", "a", "an", "in", "on", "to", "for", "by", "with", "at", "from", "as", "is"}

class QuestionMatcher:
    def get_user_learning_state(uid: str, course: str) -> Optional[dict]:
        doc = db.collection("learning").document(uid).collection("courses").document(course).get()
        return doc.to_dict() if doc.exists else None
    
    def split_tags(tags: Iterable[str]) -> Set[str]:
        words = set()
        for tag in tags:
            tag = tag.lower()
            # Replace hyphens and slashes with spaces, remove punctuation
            tag = re.sub(r"[-/]", " ", tag)
            tag = re.sub(r"[^\w\s]", "", tag)

            # Split into words and remove stopwords
            for word in tag.split():
                if word in STOPWORDS or not word.strip():
                    continue
                # Simple lemmatization: convert plurals ending in 's' to singular
                if word.endswith("s") and len(word) > 3:
                    word = word[:-1]
                words.add(word)
        return words

    def get_question_tags(self, question_ids: List[str]) -> Set[str]:
        tags = set()
        for qid in question_ids:
            doc = db.collection("questions").document(qid).get()
            if doc.exists:
                raw_tags = doc.to_dict().get("tags", [])
                tags.update(self.split_tags(raw_tags))
        return tags

    def get_course_tags(self, course_id: str) -> Set[str]:
        doc = db.collection("course").document(course_id).get()
        if doc.exists:
            raw_tags = doc.to_dict().get("tags", [])
            return self.split_tags(raw_tags)
        return set()

    def get_unit_tags(self, course_id: str, unit_id: Optional[str]) -> Set[str]:
        if not unit_id:
            return set()
        doc = (
            db.collection("course")
            .document(course_id)
            .collection("units")
            .document(unit_id)
            .get()
        )
        if doc.exists:
            raw_tags = doc.to_dict().get("tags", [])
            return self.split_tags(raw_tags)
        return set()

    def get_effective_tags(self, question: dict) -> Set[str]:
        """
        Combine question tags + course tags + unit tags for accurate context matching.
        """
        qtags = set(question.get("tags", []))
        course_id = question.get("course")
        unit_id = question.get("unit")
        return qtags | self.get_course_tags(course_id) | self.get_unit_tags(course_id, unit_id)
    
    def find_relevant_questions(
        self,
        liked_tags: Set[str],
        disliked_tags: Set[str],
        course_tags: Set[str],
        unit_tags: Set[str],
        answered_questions: Set[str],
        subscribed_courses: Set[str],
        match_threshold: float = 0.5,
        disliked_threshold: float = 0.4,
    ) -> List[Dict]:
        """
        Finds relevant questions for a user based on:
        - Curriculum alignment (≥ match_threshold of course+unit tags must be present in question)
        - Dislike filtering (≤ disliked_threshold of question tags may be disliked)
        - Penalizes answered questions but still includes them

        Returns a flat list of matched question dicts with course/unit/question IDs and scoring info.
        """
        matched = []
        curriculum_tags = course_tags | unit_tags

        for doc in db.collection("questions").stream():
            qdata = doc.to_dict()
            qid = doc.id

            # STEP 1: Get all tags related to question, split multi-word tags
            effective_tags = self.get_effective_tags(qdata)
            if not effective_tags:
                continue

            # STEP 2: Check proportion of disliked tags (excluding those allowed by curriculum)
            disallowed_disliked_tags = effective_tags & disliked_tags - curriculum_tags
            dislike_ratio = len(disallowed_disliked_tags) / len(effective_tags)
            if dislike_ratio > disliked_threshold:
                continue  # too many disallowed disliked tags

            # STEP 3: Check curriculum alignment
            num_required = len(curriculum_tags)
            if num_required == 0:
                continue

            num_matched = len(effective_tags & curriculum_tags)
            match_ratio = num_matched / num_required
            if match_ratio < match_threshold:
                continue

            # STEP 4: Compute scoring
            liked_overlap = len(effective_tags & liked_tags)
            liked_ratio = liked_overlap / len(effective_tags)
            liked_boost = round(liked_ratio * 2, 2)  # scale to 0–2

            course_id = qdata.get("course")
            subscribed_boost = 1 if course_id in subscribed_courses else 0

            answered_penalty = -1 if qid in answered_questions else 0

            priority = liked_boost + subscribed_boost + answered_penalty

            matched.append({
                "course_id": course_id,
                "course_name": qdata.get("course_name", ""),
                "unit_id": qdata.get("unit"),
                "unit_name": qdata.get("unit_name", ""),
                "question_id": qid,
                "score": liked_overlap,
                "priority": priority
            })

        return matched

    def group_and_rank(self, matched: List[Dict], top_k: int) -> List[Dict]:
        """
        Groups matched questions by (course_id, unit_id), 
        aggregates priority and score, and returns the top_k results 
        in the format required by the API layer.

        Sorting order:
        - Higher total priority (from liked tags + subscriptions)
        - Then higher tag match score
        """
        grouped = {}

        for item in matched:
            key = (item["course_id"], item["unit_id"])
            if key not in grouped:
                grouped[key] = {
                    "course_id": item["course_id"],
                    "course_name": item["course_name"],
                    "unit_id": item["unit_id"],
                    "unit_name": item["unit_name"],
                    "questions": [],
                    "priority": 0,
                    "total_score": 0
                }

            grouped[key]["questions"].append(item["question_id"])
            grouped[key]["priority"] += item["priority"]
            grouped[key]["total_score"] += item["score"]

        # Sort the groups
        sorted_groups = sorted(
            grouped.values(),
            key=lambda g: (-g["priority"], -g["total_score"])
        )

        top_results = sorted_groups[:top_k]
        random.shuffle(top_results)
        
        # Format result to include only desired output fields
        result = [
            {
                "course_id": group["course_id"],
                "course_name": group["course_name"],
                "unit_id": group["unit_id"],
                "unit_name": group["unit_name"],
                "questions": group["questions"]
            }
            for group in sorted_groups[:top_k]
        ]

        return result

matcher = QuestionMatcher()


@question_match.route("/find_similar_courses", methods=["POST"])
def find_similar_courses():
    data = request.json
    uid = data.get("uid")
    course_id = data.get("course_id")
    unit_id = data.get("unit_id")
    use_units = data.get("useUnits", False)
    top_k = data.get("top_k", 5)

    if not uid or not course_id:
        return jsonify({"error": "Missing required fields"}), 400

    # Step 1: Load user's learning state for this course
    user_data = matcher.get_user_learning_state(uid, course_id)
    if not user_data:
        return jsonify({"error": "User not found"}), 404

    liked_ids = user_data.get("likedQuestions", [])
    disliked_ids = user_data.get("dislikedQuestions", [])
    answered_ids = set(user_data.get("answeredQuestions", []))
    subscribed_courses = set(user_data.get("subscribedCourses", []))

    # Step 2: Extract tags from questions and course/unit metadata
    liked_tags = matcher.get_question_tags(liked_ids)
    disliked_tags = matcher.get_question_tags(disliked_ids)
    course_tags = matcher.get_course_tags(course_id)
    unit_tags = matcher.get_unit_tags(course_id, unit_id) if use_units and unit_id else set()

    # Step 3: Match relevant questions (curriculum match is mandatory)
    matched = matcher.find_relevant_questions(
        liked_tags=liked_tags,
        disliked_tags=disliked_tags,
        course_tags=course_tags,
        unit_tags=unit_tags,
        answered_questions=answered_ids,
        subscribed_courses=subscribed_courses,
        match_threshold=0.5,      # curriculum match ratio required
        disliked_threshold=0.4    # tolerated disliked tag ratio
    )

    # Step 4: Group results by course/unit and return top-k
    result = matcher.group_and_rank(matched, top_k)
    return jsonify({"similar_courses": result}), 200
