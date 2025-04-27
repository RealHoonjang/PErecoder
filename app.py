from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, flash
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import matplotlib
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session as flask_session

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')
Base = declarative_base()

# 데이터베이스 설정
engine = create_engine('sqlite:///pe_records.db')
Session = sessionmaker(bind=engine)

# 데이터베이스 모델 정의
class Student(Base):
    __tablename__ = 'students'
    id = Column(Integer, primary_key=True)
    class_number = Column(String(10))
    student_number = Column(String(10))
    name = Column(String(50))
    user_id = Column(Integer)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)

class ExerciseRecord(Base):
    __tablename__ = 'exercise_records'
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer)
    date = Column(Date)
    exercise_type = Column(String(50))
    value = Column(Float)
    user_id = Column(Integer)

class ExerciseType(Base):
    __tablename__ = 'exercise_types'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    user_id = Column(Integer)

# 데이터베이스 테이블 생성
Base.metadata.create_all(engine)

print("서버 실행 시작")

matplotlib.rc('font', family='Malgun Gothic')  # 윈도우 한글 폰트
matplotlib.rcParams['axes.unicode_minus'] = False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_students', methods=['POST'])
def upload_students():
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다.'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '선택된 파일이 없습니다.'}), 400
    
    if not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'error': '엑셀 파일(.xlsx, .xls)만 업로드 가능합니다.'}), 400
    
    session = Session()
    try:
        user_id = flask_session['user_id']
        # 파일을 메모리에 로드
        file_content = file.read()
        df = pd.read_excel(BytesIO(file_content))
        
        # 필수 컬럼 확인
        if '이름' not in df.columns and '성명' in df.columns:
            df = df.rename(columns={'성명': '이름'})
        required_columns = ['반', '번호', '이름']
        if not all(col in df.columns for col in required_columns):
            return jsonify({'error': '엑셀 파일에 반, 번호, 이름(또는 성명) 컬럼이 필요합니다.'}), 400
        
        # 기존 데이터 삭제 (해당 user_id만)
        session.query(Student).filter_by(user_id=user_id).delete()
        
        # 데이터 추가
        for _, row in df.iterrows():
            try:
                student = Student(
                    class_number=str(row['반']),
                    student_number=str(row['번호']),
                    name=str(row['이름']),
                    user_id=user_id
                )
                session.add(student)
            except Exception as e:
                session.rollback()
                return jsonify({'error': f'데이터 처리 중 오류가 발생했습니다: {str(e)}'}), 500
        
        session.commit()
        return jsonify({'message': '학생 정보가 성공적으로 업로드되었습니다.'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': f'업로드 중 오류가 발생했습니다: {str(e)}'}), 500
    finally:
        session.close()

@app.route('/get_students')
def get_students():
    session = Session()
    try:
        user_id = flask_session['user_id']
        students = session.query(Student).filter_by(user_id=user_id).all()
        student_list = [{
            'id': student.id,
            'class_number': student.class_number,
            'student_number': student.student_number,
            'name': student.name
        } for student in students]
        return jsonify(student_list)
    finally:
        session.close()

@app.route('/add_record', methods=['POST'])
def add_record():
    data = request.json
    session = Session()
    try:
        user_id = flask_session['user_id']
        # 학생이 해당 user_id의 학생인지 확인
        student = session.query(Student).filter_by(id=data['student_id'], user_id=user_id).first()
        if not student:
            return jsonify({'error': '해당 학생을 찾을 수 없습니다.'}), 400
        record = ExerciseRecord(
            student_id=data['student_id'],
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            exercise_type=data['exercise_type'],
            value=float(data['value']),
            user_id=user_id
        )
        session.add(record)
        session.commit()
        return jsonify({'message': '기록이 성공적으로 추가되었습니다.'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/get_records/<int:student_id>')
def get_records(student_id):
    session = Session()
    try:
        user_id = flask_session['user_id']
        # 해당 user_id의 학생만
        student = session.query(Student).filter_by(id=student_id, user_id=user_id).first()
        if not student:
            return jsonify([])
        records = session.query(ExerciseRecord).filter_by(student_id=student_id, user_id=user_id).order_by(ExerciseRecord.date).all()
        data = [{
            'id': record.id,
            'date': record.date.strftime('%Y-%m-%d'),
            'exercise_type': record.exercise_type,
            'value': record.value
        } for record in records]
        return jsonify(data)
    finally:
        session.close()

@app.route('/get_graph/<int:student_id>')
def get_graph(student_id):
    session = Session()
    try:
        user_id = flask_session['user_id']
        student = session.query(Student).filter_by(id=student_id, user_id=user_id).first()
        if not student:
            return jsonify({'error': '기록이 없습니다.'}), 404
        records = session.query(ExerciseRecord).filter_by(student_id=student_id, user_id=user_id).order_by(ExerciseRecord.date).all()
        if not records:
            return jsonify({'error': '기록이 없습니다.'}), 404
        values = [record.value for record in records]
        labels = [f"{i+1}회\n{record.exercise_type}" for i, record in enumerate(records)]
        plt.figure(figsize=(12, 6))
        plt.plot(range(1, len(values)+1), values, marker='o', linestyle='-', linewidth=2, markersize=8, color='#4a90e2')
        for i, (x, y) in enumerate(zip(range(1, len(values)+1), values)):
            plt.text(x, y, f"{records[i].exercise_type}", fontsize=10, ha='center', va='bottom')
        plt.title(f'{student.name} 학생의 운동 기록', fontsize=14, pad=20)
        plt.xlabel('입력 회차', fontsize=12)
        plt.ylabel('기록', fontsize=12)
        plt.xticks(range(1, len(values)+1), labels, rotation=30, ha='right')
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        img = BytesIO()
        plt.savefig(img, format='png', dpi=100)
        img.seek(0)
        plt.close()
        return send_file(img, mimetype='image/png')
    finally:
        session.close()

@app.route('/delete_record/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    session = Session()
    try:
        user_id = flask_session['user_id']
        record = session.query(ExerciseRecord).filter_by(id=record_id, user_id=user_id).first()
        if not record:
            return jsonify({'error': '기록을 찾을 수 없습니다.'}), 404
        session.delete(record)
        session.commit()
        return jsonify({'message': '기록이 삭제되었습니다.'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        session_db = Session()
        if session_db.query(User).filter_by(username=username).first():
            flash('이미 존재하는 아이디입니다.', 'danger')
            return redirect(url_for('register'))
        user = User(username=username, password_hash=generate_password_hash(password))
        session_db.add(user)
        session_db.commit()
        session_db.close()
        flash('회원가입이 완료되었습니다. 로그인 해주세요.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        session_db = Session()
        user = session_db.query(User).filter_by(username=username).first()
        session_db.close()
        if user and check_password_hash(user.password_hash, password):
            flask_session['user_id'] = user.id
            flask_session['username'] = user.username
            flash('로그인 성공!', 'success')
            return redirect(url_for('index'))
        else:
            flash('아이디 또는 비밀번호가 올바르지 않습니다.', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    flask_session.clear()
    flash('로그아웃 되었습니다.', 'info')
    return redirect(url_for('login'))

@app.before_request
def require_login():
    allowed_routes = ['login', 'register', 'static']
    if request.endpoint not in allowed_routes and 'user_id' not in flask_session:
        return redirect(url_for('login'))

@app.route('/add_exercise_type', methods=['POST'])
def add_exercise_type():
    data = request.json
    name = data.get('name')
    user_id = flask_session['user_id']
    session = Session()
    try:
        if session.query(ExerciseType).filter_by(name=name, user_id=user_id).first():
            return jsonify({'error': '이미 존재하는 종목입니다.'}), 400
        etype = ExerciseType(name=name, user_id=user_id)
        session.add(etype)
        session.commit()
        return jsonify({'message': '종목이 추가되었습니다.'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/delete_exercise_type/<int:type_id>', methods=['DELETE'])
def delete_exercise_type(type_id):
    user_id = flask_session['user_id']
    session = Session()
    try:
        etype = session.query(ExerciseType).filter_by(id=type_id, user_id=user_id).first()
        if not etype:
            return jsonify({'error': '종목을 찾을 수 없습니다.'}), 404
        session.delete(etype)
        session.commit()
        return jsonify({'message': '종목이 삭제되었습니다.'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/get_exercise_types')
def get_exercise_types():
    user_id = flask_session['user_id']
    session = Session()
    try:
        types = session.query(ExerciseType).filter_by(user_id=user_id).all()
        return jsonify([{'id': t.id, 'name': t.name} for t in types])
    finally:
        session.close()

@app.route('/add_student', methods=['POST'])
def add_student():
    data = request.json
    user_id = flask_session['user_id']
    session = Session()
    try:
        student = Student(
            class_number=data['class_number'],
            student_number=data['student_number'],
            name=data['name'],
            user_id=user_id
        )
        session.add(student)
        session.commit()
        return jsonify({'message': '학생이 추가되었습니다.'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/get_classes')
def get_classes():
    user_id = flask_session['user_id']
    session = Session()
    try:
        classes = session.query(Student.class_number).filter_by(user_id=user_id).distinct().all()
        return jsonify([c[0] for c in classes])
    finally:
        session.close()

@app.route('/get_students_by_class/<class_number>')
def get_students_by_class(class_number):
    user_id = flask_session['user_id']
    session = Session()
    try:
        students = session.query(Student).filter_by(user_id=user_id, class_number=class_number).all()
        student_list = [{
            'id': student.id,
            'student_number': student.student_number,
            'name': student.name
        } for student in students]
        return jsonify(student_list)
    finally:
        session.close()

@app.route('/delete_all_students', methods=['DELETE'])
def delete_all_students():
    user_id = flask_session['user_id']
    session = Session()
    try:
        # 학생 id 목록
        student_ids = [s.id for s in session.query(Student).filter_by(user_id=user_id).all()]
        # 운동 기록 삭제
        session.query(ExerciseRecord).filter(ExerciseRecord.student_id.in_(student_ids)).delete(synchronize_session=False)
        # 학생 삭제
        session.query(Student).filter_by(user_id=user_id).delete()
        session.commit()
        return jsonify({'message': '학생 명단이 모두 삭제되었습니다.'})
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/download_class_records/<class_number>')
def download_class_records(class_number):
    user_id = flask_session['user_id']
    session = Session()
    try:
        # 해당 반의 학생 조회
        students = session.query(Student).filter_by(user_id=user_id, class_number=class_number).all()
        if not students:
            return jsonify({'error': '해당 반의 학생이 없습니다.'}), 404

        # 학생별 기록 정리
        data = []
        for student in students:
            # 학생의 모든 기록을 종목별로 묶기
            records = session.query(ExerciseRecord).filter_by(student_id=student.id, user_id=user_id).order_by(ExerciseRecord.exercise_type, ExerciseRecord.date).all()
            # 종목별로 그룹핑
            record_dict = {}
            for rec in records:
                if rec.exercise_type not in record_dict:
                    record_dict[rec.exercise_type] = []
                record_dict[rec.exercise_type].append(rec.value)
            # 각 종목별로 한 줄씩
            for exercise_type, values in record_dict.items():
                row = {
                    '반': student.class_number,
                    '번호': student.student_number,
                    '성명': student.name,
                    '종목': exercise_type
                }
                # 회차별 기록
                for idx, v in enumerate(values, 1):
                    row[f'{idx}회차'] = v
                data.append(row)
        if not data:
            return jsonify({'error': '기록이 없습니다.'}), 404

        df = pd.DataFrame(data)
        # 컬럼 순서 정렬
        base_cols = ['반', '번호', '성명', '종목']
        other_cols = sorted([c for c in df.columns if c not in base_cols], key=lambda x: int(x.replace('회차','').replace(' ','').replace('차','')) if '회차' in x else 0)
        df = df[base_cols + other_cols]

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name=f"{class_number}반")
        output.seek(0)
        filename = f"{class_number}반_기록.xlsx"
        return send_file(output, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    finally:
        session.close()

if __name__ == '__main__':
    app.run(debug=True) 
