import pandas as pd
from datetime import timezone
from dateutil.parser import parse
from werkzeug.security import generate_password_hash

from app import app, db, User, Review


def import_from_csv(file_path: str, batch_size: int = 500):
    # ---------- 1. читаем файл ------------------------------------------------
    df = pd.read_csv(file_path, dtype=str)
    df.dropna(subset=['Оценка','Время','Текст', 'Компания'], how='any', inplace=True)
    df= df.sample(n=1000, random_state=42)
    print(f"Начинаем импорт {len(df)} записей…")


    with app.app_context():
        # ---------- 2. при необходимости чистим БД ---------------------------
        db.drop_all()
        db.create_all()

        users_cache = {}
        total_imported = 0
        batch_num = 0

        # ---------- 3. проходимся по DataFrame -----------------------------------
        for idx, row in df.iterrows():

            # ---- 3.1 пользователь -----------------------------------------
            username = str(row.get('Пользователь', '')).strip()
            if not username:
                print(f"⏩ строка {idx}: нет имени пользователя")
                continue

            # кешируем (чтобы не тащить запрос к БД на каждую строку)
            user = users_cache.get(username)
            if not user:
                user = User(
                    username=username,
                    email=f"{username}@example.com",
                    password_hash=generate_password_hash("defaultpassword")
                )
                db.session.add(user)
                db.session.flush()              # ← получаем user.id тут же
                users_cache[username] = user

            # ---- 3.2 создаём отзыв -------------------------------------
            raw_time = str(row.get('Время', '')).strip()
            try:
                created_at = (parse(raw_time, dayfirst=True)
                              .replace(tzinfo=timezone.utc))
            except Exception:
                created_at = pd.Timestamp.utcnow().to_pydatetime()
                print(f"⚠️  строка {idx}: не смог распарсить время «{raw_time}», "
                      f"ставлю текущий момент")

            req_fields = ['Заголовок', 'Текст', 'Оценка', 'Компания', 'Category']
            if any(not str(row.get(f, '')).strip() for f in req_fields):
                print(f"⏩ строка {idx}: отсутствуют обязательные данные")
                continue

            try:
                rating_val = int(float(row['Оценка']))
            except Exception:
                rating_val = None

            review = Review(
                title=row['Заголовок'],
                content=row['Текст'],
                rating=rating_val,
                bank=row['Компания'],
                created_at=created_at,
                user_id=user.id,
                category=row['Category']
            )
            db.session.add(review)
            total_imported += 1

            # ---- 3.3 фиксация батча ----------------------------------------
            if total_imported % batch_size == 0:
                db.session.commit()
                batch_num += 1
                print(f"✓ батч #{batch_num}: ещё {batch_size} записей")

        # ---------- 4. фиксируем «хвост» -------------------------------------
        db.session.commit()
        print(f"Импорт завершён: всего {total_imported} записей.")


if __name__ == "__main__":
    import_from_csv("static/classified_reviews_full.csv")
