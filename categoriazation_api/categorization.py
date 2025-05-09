from flask import Flask, request, jsonify
import joblib


# Загрузка моделей и векторизатора
vectorizer = joblib.load("config/tfidf_vectorizer.pkl")
kmeans_model = joblib.load("config/kmeans_model.pkl")
category_mapping = joblib.load("config/category_mapping.pkl")

# Создание Flask-приложения
app = Flask(__name__)

# Функция для предсказания категории
def predict_category(review_text):
    processed_text = ' '.join([word for word in review_text.split()])
    vectorized_text = vectorizer.transform([processed_text])
    cluster = kmeans_model.predict(vectorized_text)[0]
    return category_mapping.get(cluster, "Неизвестная категория")

# Эндпоинт для предсказания категории
@app.route("/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()
        review_text = data.get("text")
        if not review_text:
            return jsonify({"error": "Поле 'text' обязательно"}), 400

        category = predict_category(review_text)
        return jsonify({"category": category})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Запуск приложения
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)