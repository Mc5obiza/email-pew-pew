def word_count(text: str) -> int:
    return len([word for word in text.replace("\n", " ").split(" ") if word.strip()])
