from typing import List, Optional, TypedDict

class Hint(TypedDict):
    key: str
    title: str
    content: str
    image: str

class Answer(TypedDict): 
    id: str
    text: str
    correct: bool
    hint: Optional[Hint]

class Question(TypedDict):
    id: str
    question: str
    hints: List[Hint]
    answers: List[Answer]
    course: str
    unit: str