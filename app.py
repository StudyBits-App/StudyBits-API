from flask import Flask
from Blueprints.QuestionMatcher import question_match

app = Flask(__name__)
app.register_blueprint(question_match)

if __name__ == "__main__":
    app.run(debug=True)
