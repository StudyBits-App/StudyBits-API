from flask import Blueprint, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types
from typing import List, Optional
import os
import base64
import requests
from firebase.firebase import db
from util.classes import Question

classify = Blueprint('classify', __name__,)
load_dotenv()

class Classifier:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    def getQuestionData(self, doc_id: str) -> Optional[Question]:
        doc_ref = db.collection("questions").document(doc_id)
        doc = doc_ref.get()

        if not doc.exists:
            print(f"Question with ID {doc_id} not found.")
            return None

        data = doc.to_dict()
        return data  
    
    def classifyQuestion(self, question: Question) -> List[str]:
        parts: list[types.Part] = []

        parts.append(types.Part(text=
            "You are designed to classify questions with tags.\n"
            "Given the following question and any associated hints (text possibly with an image), "
            "return a comma-separated list of appropriate tags from broad to specific.\n\n"
            f"Question:\n{question['question']}\n\nHints:"
        ))

        for hint in question.get("hints", []):
            title = hint.get("title")
            content = hint.get("content", "")

            if title:
                parts.append({
                    "text": f"\n\nHint Title: {title}\nHint Content: {content}"
                })
            else:
                parts.append({
                    "text": f"\n\nHint Content: {content}"
                })
            image_url = hint.get("image")
            if image_url and image_url.startswith("http"):
                try:
                    image_bytes = requests.get(image_url).content
                    base64_data = base64.b64encode(image_bytes).decode("utf-8")
                    parts.append({
                        "inline_data": {
                            "mime_type": "image/png",  
                            "data": base64_data
                        }
                    })
                except Exception as e:
                    print(f"Error fetching image from {image_url}: {e}")


        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=parts
        )

        raw = response.text.strip()
        tags = [
            tag.strip().lower()
            for tag in raw.replace("[", "").replace("]", "").replace('"', "").split(",")
            if tag.strip()
        ]

        return list(dict.fromkeys(tags))

    def getQuestionTags(self, doc_id: str) -> Optional[str]:
        question = self.getQuestionData(doc_id)
        if question is None:
            return None
        return self.classifyQuestion(question)
    
    def classifyCourse(self, course_name: str) -> List[str]:
        prompt = (
            "You are designed to classify courses into broad and specific subject tags.\n"
            "Given the course name, return a comma-separated list of relevant tags, "
            "from broad to specific.\n\n"
            f"Course Name: {course_name}\n"
        )
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        raw = response.text.strip()
        tags = [
            tag.strip().lower()
            for tag in raw.replace("[", "").replace("]", "").replace('"', "").split(",")
            if tag.strip()
        ]
        return list(dict.fromkeys(tags))

    def classifyUnit(self, unit_name: str) -> List[str]:
        prompt = (
            "You are designed to classify units of study into relevant subject tags.\n"
            "Given the unit's name, return a comma-separated list of lowercase tags "
            "from broad to specific.\n\n"
            f"Unit Name: {unit_name}"
        )
        
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        raw = response.text.strip()
        tags = [
            tag.strip().lower()
            for tag in raw.replace("[", "").replace("]", "").replace('"', "").split(",")
            if tag.strip()
        ]
        return list(dict.fromkeys(tags))

classifier = Classifier()

@classify.route('/questionClassify', methods=['POST'])
def questionClassify():
    data = request.json
    question_id = data.get('question_id')
    if not question_id:
        return jsonify({"error": "Missing 'question_id'"}), 400

    tags = classifier.getQuestionTags(question_id)
    if tags is None:
        return jsonify({"error": "No tags"}), 404

    return jsonify({"tags": tags})

@classify.route('/courseClassify', methods=['POST'])
def courseClassify():
    data = request.json
    course_name = data.get('course_name')

    if not course_name:
        return jsonify({"error": "Missing 'course_name'"}), 400

    tags = classifier.classifyCourse(course_name)
    if tags is None:
        return jsonify({"error": "No tags"}), 404

    return jsonify({"tags": tags})


@classify.route('/unitClassify', methods=['POST'])
def unitClassify():
    data = request.json
    unit_name = data.get('unit_name')

    if not unit_name:
        return jsonify({"error": "Missing 'unit_name'"}), 400

    tags = classifier.classifyUnit({
        "unit_name": unit_name,
    })
    if tags is None:
        return jsonify({"error": "No tags"}), 404

    return jsonify({"tags": tags})
