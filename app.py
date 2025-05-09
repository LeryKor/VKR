from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, PasswordField,  SelectField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
import requests
from datetime import datetime, timezone
from sqlalchemy import func
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SECRET_KEY'] = 'supersecretkey'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    reviews = db.relationship('Review', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=True)  # Заголовок
    content = db.Column(db.Text, nullable=False)       # Текст
    rating = db.Column(db.Integer, nullable=False)     # Оценка
    bank = db.Column(db.String(100), nullable=False) # Компания
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))  # Время
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Пользователь
    category = db.Column(db.String(100), nullable=True) # Категория

    def __repr__(self):
        return f'<Review {self.title} by {self.author.username}>'


class ReviewForm(FlaskForm):
    content = TextAreaField('Отзыв', validators=[DataRequired()])
    bank = StringField('Банк', validators=[DataRequired()])
    rating = SelectField('Оценка', choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')], coerce=int, validators=[DataRequired()])
    submit = SubmitField('Добавить отзыв')

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=3, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Повторите пароль', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')

def categorize_review(text):
    url = "http://127.0.0.1:5050/predict"
    response = requests.post(url, json={"text": text})
    if response.status_code == 200:
        return response.json().get("category", "Неизвестная категория")
    return "Ошибка категоризации"


# Добавим список популярных банков
POPULAR_BANKS = ['Сбербанк', 'Тинькофф', 'ВТБ', 'Альфа-Банк', 'Газпромбанк', 'Райффайзенбанк']

@app.context_processor
def inject_user():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            return {'user': user.username}
    return {'user': None}


@app.route('/')
def index():
    page            = request.args.get('page', 1, type=int)
    category_filter = request.args.get('category')
    bank_filter     = request.args.get('bank')
    sort            = request.args.get('sort', 'newest')
    date_from_str   = request.args.get('date_from')
    date_to_str     = request.args.get('date_to')

    query = Review.query

    # --- фильтры ---
    if category_filter:
        query = query.filter_by(category=category_filter)
    if bank_filter:
        query = query.filter_by(bank=bank_filter)
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            query = query.filter(Review.created_at >= date_from)
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = (datetime.strptime(date_to_str, '%Y-%m-%d')
                       .replace(tzinfo=timezone.utc, hour=23, minute=59, second=59))
            query = query.filter(Review.created_at <= date_to)
        except ValueError:
            pass

    # --- сортировка ---
    if sort == 'newest':
        query = query.order_by(Review.id.desc())
    elif sort == 'oldest':
        query = query.order_by(Review.id.asc())
    elif sort == 'highest':
        query = query.order_by(Review.rating.desc())
    elif sort == 'lowest':
        query = query.order_by(Review.rating.asc())

    reviews    = query.paginate(page=page, per_page=5)
    categories = [c[0] for c in db.session.query(Review.category).distinct() if c[0]]
    banks      = [b[0] for b in db.session.query(Review.bank).distinct() if b[0]]

    return render_template('index.html',
                           reviews=reviews,
                           categories=categories,
                           banks=banks)


@app.route('/add_review', methods=['GET', 'POST'])
def add_review():
    if 'user_id' not in session:
        flash('Войдите в систему, чтобы оставить отзыв', 'warning')
        return redirect(url_for('login'))

    form = ReviewForm()
    if form.validate_on_submit():
        category = categorize_review(form.content.data)
        new_review = Review(
            content=form.content.data,
            category=category,
            bank=form.bank.data,
            rating=form.rating.data,
            user_id=session['user_id']
        )
        db.session.add(new_review)
        db.session.commit()
        flash('Отзыв добавлен!', 'success')
        return redirect(url_for('index'))

    return render_template('add_review.html',
                           form=form,
                           popular_banks=POPULAR_BANKS)


@app.route('/profile/<username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template(
        'profile.html',
        username=user.username,
        reviews=user.reviews
    )




@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        # Проверяем, нет ли уже пользователя с таким email или username
        existing_user = User.query.filter((User.email == form.email.data) |
                                          (User.username == form.username.data)).first()
        if existing_user:
            if existing_user.email == form.email.data:
                flash('Пользователь с таким email уже существует', 'danger')
            else:
                flash('Пользователь с таким именем уже существует', 'danger')
            return render_template('register.html', form=form)

        try:
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))  # Перенаправляем на страницу входа
        except Exception as e:
            db.session.rollback()
            flash('Произошла ошибка при регистрации. Пожалуйста, попробуйте позже.', 'danger')

    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Вы успешно вошли!', 'success')
            return redirect(url_for('index'))
        flash('Неверные email или пароль', 'danger')
    return render_template('login.html', form=form)


@app.after_request
def add_no_cache(response):
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.route('/logout')
def logout():
    # Очищаем всю сессию полностью
    session.clear()
    # Устанавливаем заголовки, запрещающие кэширование
    response = redirect(url_for('index'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    flash('Вы успешно вышли из системы', 'success')
    return response

@app.route('/analytics')
def analytics():
    category = request.args.get('category')
    bank = request.args.get('bank')
    r_min = request.args.get('rating_min', 1, type=int)
    r_max = request.args.get('rating_max', 5, type=int)
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')

    q = Review.query
    if category:
        q = q.filter_by(category=category)
    if bank:
        q = q.filter_by(bank=bank)
    q = q.filter(Review.rating.between(r_min, r_max))

    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            q = q.filter(Review.created_at >= date_from)
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = (datetime.strptime(date_to_str, '%Y-%m-%d')
                       .replace(tzinfo=timezone.utc, hour=23, minute=59, second=59))
            q = q.filter(Review.created_at <= date_to)
        except ValueError:
            pass

    # ---------- метрики ----------
    per_category     = q.with_entities(Review.category, func.count(Review.id)).group_by(Review.category)
    avg_rating_cat   = q.with_entities(Review.category, func.avg(Review.rating)).group_by(Review.category)
    per_bank         = q.with_entities(Review.bank, func.count(Review.id)).group_by(Review.bank)
    avg_rating_bank  = q.with_entities(Review.bank, func.avg(Review.rating)).group_by(Review.bank)
    rating_dist      = q.with_entities(Review.rating, func.count(Review.id)).group_by(Review.rating)
    over_time        = (q.with_entities(func.strftime('%Y-%m', Review.created_at).label('ym'),
                                        func.count(Review.id))
                           .group_by('ym').order_by('ym').all())
    avg_rating_time = (q.with_entities(
        func.strftime('%Y-%m', Review.created_at).label('ym'),
        func.avg(Review.rating))
                       .group_by('ym')
                       .order_by('ym')
                       .all())

    chart_data = {
        'per_category':     dict(labels=[c or 'Не указано' for c, _ in per_category],
                                 values=[cnt for _, cnt in per_category]),
        'avg_rating':       dict(labels=[c or 'Не указано' for c, _ in avg_rating_cat],
                                 values=[round(r, 2) for _, r in avg_rating_cat]),
        'per_bank':         dict(labels=[b for b, _ in per_bank],
                                 values=[cnt for _, cnt in per_bank]),
        'avg_rating_bank':  dict(labels=[b for b, _ in avg_rating_bank],
                                 values=[round(r, 2) for _, r in avg_rating_bank]),
        'rating_distribution': dict(labels=[str(r) for r, _ in rating_dist],
                                    values=[cnt for _, cnt in rating_dist]),
        'over_time': {
            'labels': [f'{d}-01' for d, _ in over_time],
            'values': [cnt for _, cnt in over_time]
        },
        'avg_rating_time': {
            'labels': [f'{d}-01' for d, _ in avg_rating_time],
            'values': [round(r, 2) for _, r in avg_rating_time]
        }
    }

    categories = [c[0] for c in db.session.query(Review.category).distinct() if c[0]]
    banks      = [b[0] for b in db.session.query(Review.bank).distinct() if b[0]]

    return render_template('analytics.html',
                           chart_data=json.dumps(chart_data, ensure_ascii=False),
                           categories=categories,
                           banks=banks)



if __name__ == '__main__':
    with app.app_context():
        # Проверяем существование столбцов
        inspector = db.inspect(db.engine)
        columns = inspector.get_columns('review')
        column_names = [col['name'] for col in columns]

        # if 'bank' not in column_names or 'rating' not in column_names:
        #     db.drop_all()
        #     db.create_all()

    app.run(debug=True)