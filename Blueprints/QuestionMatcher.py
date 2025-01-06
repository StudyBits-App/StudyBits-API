from flask import Blueprint, request, jsonify
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from utils.similarity_calculator import Similarity
import firebase_admin
import os
import json

question_match = Blueprint('question_match', __name__,)
load_dotenv()

class QuestionMatcher:
    def __init__(self):
        firebase_cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
        if firebase_cred_json:
            firebase_cred_dict = json.loads(firebase_cred_json)
            self._initialize_firebase(firebase_cred_dict)

    def _initialize_firebase(self, cred_dict):
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()
    
    def compute_similarity(self, string1: str, string2: str) -> float:
        return Similarity().compute_similarity(string1, string2)

    def get_course(self, course_id):
        course_ref = self.db.collection('courses').document(course_id)
        course = course_ref.get().to_dict()
        if not course:
            raise Exception(f"Course with ID {course_id} not found.")
        return course

    def get_unit(self, course_id, unit_id):
        unit= self.db.collection('courses').document(course_id).collection('units').document(unit_id).get().to_dict()
        if not unit:
            raise Exception(f"Unit with ID {unit_id} not found in Course {course_id}.")
        return unit
    
    def filter_similar_courses(self, target_course, course_similarity_threshold):
        courses = self.db.collection('courses').stream()
        similar_courses = []
        for course in courses:
            course_data = course.to_dict()     
            course_similarity_score = self.compute_similarity(target_course.get('name'), course_data.get('name'))
            if course_similarity_score >= course_similarity_threshold:
                similar_courses.append((course.id, course_data, course_similarity_score))

        return similar_courses  
    
    def find_similar_units(self, target_unit_text, course_id, unit_similarity_threshold):
        try:
            units = self.db.collection('courses').document(course_id).collection('units').stream()

            similar_units = []
            for unit in units:
                unit_data = unit.to_dict()
                unit_text = unit_data.get('name') + " " + unit_data.get('description')
                similarity_score = self.compute_similarity(target_unit_text, unit_text)

                if similarity_score >= unit_similarity_threshold and unit_data.get('questions'):
                    similar_units.append((
                        unit.id,
                        unit_data.get('name'), 
                        similarity_score,
                        unit_data.get('questions', [])
                    ))

            similar_units.sort(key=lambda x: x[2], reverse=True)
            return similar_units
        except Exception as e:
            print(f"Error finding similar units: {e}")
            return []

    def find_courses_units_questions(self, course_id, top_k, unit_id=None, unit_similarity_threshold=0.5, course_similarity_threshold=0.5):
        
        target_course = self.get_course(course_id) 
        similar_courses = self.filter_similar_courses(target_course, course_similarity_threshold)
        similar_course_data = []
        if unit_id:
            target_unit = self.get_unit(course_id, unit_id)
            target_unit_text = f"{target_unit.get('name')} {target_unit.get('description', '')}"

            for similar_course_id, course_data, _ in similar_courses:
                if not course_data.get("numQuestions") or course_data.get("numQuestions") < 1:
                    continue
                
                similar_units = self.find_similar_units(target_unit_text, similar_course_id, unit_similarity_threshold)

                for unit in similar_units:
                    similar_course_data.append({
                        "course_id": similar_course_id,
                        "course_name": course_data["name"],
                        "unit_id": unit[0],
                        "unit_name": unit[1],
                        "questions": unit[3]
                    })
        else:
            for similar_course_id, course_data, _ in similar_courses[:top_k]:
                units_ref = self.db.collection("courses").document(similar_course_id).collection("units")
                units = units_ref.stream()
                if not course_data.get("numQuestions") or course_data.get("numQuestions") < 1:
                    continue
                for unit in units:

                    unit_data = unit.to_dict()
                    similar_course_data.append({
                        "course_id": similar_course_id,
                        "course_name": course_data["name"],
                        "unit_id": unit.id,
                        "unit_name": unit_data.get("name"),
                        "questions": unit_data.get("questions", [])
                    })

        return similar_course_data

similarity_calculator = QuestionMatcher()

@question_match.route('/find_similar_courses', methods=['POST'])
def find_similar_courses():
    try:
        data = request.json
        course_id = data.get('course_id')
        unit_id = data.get('unit_id')
        top_k = data.get('top_k', 5)
        unit_similarity_threshold = data.get('unit_similarity_threshold', 0.5)
        course_similarity_threshold = data.get('course_similarity_threshold', 0.5)

        if not course_id:
            return jsonify({"error": "course_id is required"}), 400

        similar_courses_or_units = similarity_calculator.find_courses_units_questions(
            course_id=course_id,
            unit_id=unit_id,
            top_k=top_k,
            unit_similarity_threshold=unit_similarity_threshold,
            course_similarity_threshold=course_similarity_threshold,
        )

        result = [
            {
                "course_id": item["course_id"],
                "course_name": item["course_name"],
                "unit_id": item["unit_id"],
                "unit_name": item["unit_name"],
                "questions": item["questions"]
            }
            for item in similar_courses_or_units
        ]

        return jsonify({"similar_courses": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
