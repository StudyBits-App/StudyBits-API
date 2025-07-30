from flask import Flask
from flask_cors import CORS
from Blueprints.QuestionMatcher import question_match
from Blueprints.Classify import classify


app = Flask(__name__)
CORS(app)
app.register_blueprint(question_match)
app.register_blueprint(classify)
if __name__ == "__main__":
    app.run(debug=True)
