from flask import Blueprint, request, jsonify
from sentence_transformers import SentenceTransformer, util
from firebase_admin import credentials, firestore
import firebase_admin

question_match = Blueprint('question_match', __name__,)

class QuestionMatcher:
    def __init__(self, model_name="all-MiniLM-L6-v2", firebase_cred_path=None):
        self.model = SentenceTransformer(model_name)
        if firebase_cred_path:
            self._initialize_firebase(firebase_cred_path)
    
    def compute_similarity(self, string1, string2):
        embeddings = self.model.encode([string1, string2], convert_to_tensor=True)
        similarity_score = util.cos_sim(embeddings[0], embeddings[1]).item()
        return similarity_score

    def _initialize_firebase(self, cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    def get_course(self, course_id):
        course_ref = self.db.collection('courses').document(course_id)
        course = course_ref.get().to_dict()
        if not course:
            raise Exception(f"Course with ID {course_id} not found.")
        return course

    def get_unit(self, course_id, unit_id):
        unit_ref = self.db.collection('courses').document(course_id).collection('units').document(unit_id)
        unit = unit_ref.get().to_dict()
        if not unit:
            raise Exception(f"Unit with ID {unit_id} not found in Course {course_id}.")
        return unit
    
    def filter_similar_courses(self, target_course, target_course_id, course_similarity_threshold):
        courses = self.db.collection('courses').stream()
        similar_courses = []
        for course in courses:
            course_data = course.to_dict()     
            if course.id == target_course_id:
                continue

            course_similarity_score = self.compute_similarity(target_course.get('name'), course_data.get('name'))
            if course_similarity_score >= course_similarity_threshold:
                similar_courses.append((course.id, course_data, course_similarity_score))

        return similar_courses  
    
    def find_similar_units(self, target_unit_text, course_id, unit_similarity_threshold):
        try:
            units_ref = self.db.collection('courses').document(course_id).collection('units')
            units = units_ref.stream()
            
            similar_units = []
            for unit in units:
                unit_data = unit.to_dict()
                unit_text = unit_data.get('name', '') + " " + unit_data.get('description', '')
                similarity_score = self.compute_similarity(target_unit_text, unit_text)
                
            if similarity_score >= unit_similarity_threshold and unit_data.get('questions'):
                    similar_units.append((
                        unit.id,
                        unit_data.get('name', ''), 
                        similarity_score  
                    ))
            
            similar_units.sort(key=lambda x: x[2], reverse=True)
            return similar_units
        except Exception as e:
            print(f"Error finding similar units: {e}")
            return []
    
    def find_similar_courses_or_units(self, course_id, unit_id=None, top_k=5, unit_similarity_threshold=0.5, course_similarity_threshold=0.5):
        target_course = self.get_course(course_id)
        
        if unit_id:
            target_unit = self.get_unit(course_id, unit_id)
            target_unit_text = f"{target_unit.get('name', '')} {target_unit.get('description', '')}"
            
            similar_courses = self.filter_similar_courses(target_course, course_id, course_similarity_threshold)
            similarities = []

            for course_id, course_data, _ in similar_courses:
                
                if not course_data.get("numQuestions"):
                    continue

                similar_units = self.find_similar_units(target_unit_text, course_id, unit_similarity_threshold)
                
                if similar_units:
                    most_similar_unit = similar_units[0]
                    similarities.append((
                        course_id,
                        course_data['name'],
                        most_similar_unit[0],  
                        most_similar_unit[1], 
                        most_similar_unit[2],  
                    ))

            similarities.sort(key=lambda x: x[4], reverse=True)
            return similarities[:top_k]
        
        else:
            similar_courses = self.filter_similar_courses(target_course, course_id, course_similarity_threshold)
            return [
                (course_id, course_data['name']) 
                for course_id, course_data, _ in similar_courses[:top_k] 
            ]

similarity_calculator = QuestionMatcher(firebase_cred_path="studybits_firebase.json")

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
        
        similar_courses = similarity_calculator.find_similar_courses_or_units(
            course_id=course_id,
            top_k=top_k,
            unit_id=unit_id,
            unit_similarity_threshold=unit_similarity_threshold,
            course_similarity_threshold=course_similarity_threshold
        )

        result = [
            {
                "course_id": item[0], 
                "course_name": item[1],
                "unit_id": item[2] if len(item) > 2 else None
            }
            for item in similar_courses
        ]

        return jsonify({"similar_courses": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

