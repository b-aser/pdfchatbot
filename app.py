from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from dotenv import load_dotenv
import PyPDF2
from io import BytesIO
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# MySQL Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 3600,
    'pool_size': 10,
    'max_overflow': 5
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    documents = db.relationship('UserDocument', backref='owner', lazy=True, cascade='all, delete-orphan')
    chats = db.relationship('ChatHistory', backref='user', lazy=True, cascade='all, delete-orphan')

class UserDocument(db.Model):
    __tablename__ = 'user_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    file_size = db.Column(db.Integer)  # in bytes
    page_count = db.Column(db.Integer)
    processed_text = db.Column(db.Text)
    
    # Relationships
    chats = db.relationship('ChatHistory', backref='document', lazy=True, cascade='all, delete-orphan')

class ChatHistory(db.Model):
    __tablename__ = 'chat_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('user_documents.id', ondelete='CASCADE'), nullable=True)
    user_message = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_summary = db.Column(db.Boolean, default=False)
    tokens_used = db.Column(db.Integer)

# Initialize database
with app.app_context():
    db.create_all()

# Helper functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_pdf_metadata(filepath):
    try:
        with open(filepath, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
            return {
                'page_count': len(pdf_reader.pages),
                'text': text
            }
    except Exception as e:
        print(f"Error processing PDF: {e}")
        return None

# Initialize the pipeline
# chatbot = pipeline("conversational", model="methzanalytics/distilgpt2-tiny-conversational")

# Initialize model and tokenizer (load only once when app starts)
model_name = "b-aser/jku-g3-llm"  # You can change this to any Hugging Face model
tokenizer = None
model = None

def load_model():
    global tokenizer, model
    print("Loading model...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name)
    print("Model loaded successfully!")

# Load model when app starts
load_model()

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(
            username=username,
            email=email,
            password=hashed_password
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Login failed. Check username and password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

@app.route('/accountsetting')
@login_required
def accountsetting():
    return render_template('accountsetting.html')

# Main application routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_docs = UserDocument.query.filter_by(user_id=current_user.id).all()
    recent_chats = ChatHistory.query.filter_by(user_id=current_user.id)\
                        .order_by(ChatHistory.timestamp.desc())\
                        .limit(5).all()
    return render_template('dashboard.html', 
                         documents=user_docs, 
                         chats=recent_chats)

from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# Initialize AI model and tokenizer (add at the top of your app.py)
tokenizer = AutoTokenizer.from_pretrained("microsoft/DialoGPT-medium")
model = AutoModelForCausalLM.from_pretrained("microsoft/DialoGPT-medium")

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
        
        files = request.files.getlist('files')
        if not files or all(file.filename == '' for file in files):
            return jsonify({'error': 'No selected files'}), 400
        
        results = []
        
        for file in files:
            if not file or not allowed_file(file.filename):
                results.append({
                    'filename': file.filename if file else 'unknown',
                    'error': 'Invalid file type'
                })
                continue

            try:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                file.save(filepath)
                
                # Get PDF metadata
                pdf_info = extract_pdf_metadata(filepath)
                if not pdf_info:
                    results.append({
                        'filename': file.filename,
                        'error': 'Could not process PDF'
                    })
                    # Clean up failed file
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    continue
                
                # Save to database
                new_doc = UserDocument(
                    user_id=current_user.id,
                    filename=filename,
                    original_filename=file.filename,
                    filepath=filepath,
                    file_size=os.path.getsize(filepath),
                    page_count=pdf_info['page_count'],
                    processed_text=pdf_info['text']
                )
                db.session.add(new_doc)
                
                results.append({
                    'filename': file.filename,
                    'status': 'processed',
                    'doc_id': new_doc.id
                })
                
            except Exception as e:
                app.logger.error(f"Error processing file {file.filename}: {str(e)}")
                results.append({
                    'filename': file.filename,
                    'error': 'Server error processing file'
                })
                # Clean up if file was partially saved
                if 'filepath' in locals() and os.path.exists(filepath):
                    os.remove(filepath)
                continue
        
        db.session.commit()
        return jsonify({'files': results})
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': 'Server error processing request'}), 500

@app.route('/ask', methods=['POST'])
@login_required
def ask_question():
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
            
        data = request.get_json()
        question = data.get('question')
        document_id = data.get('document_id')
        
        if not question:
            return jsonify({"error": "No question provided"}), 400
        
        # Get the document if specified
        document = None
        if document_id:
            document = UserDocument.query.filter_by(
                id=document_id,
                user_id=current_user.id
            ).first()
            if not document:
                return jsonify({"error": "Document not found"}), 404
        
        # Generate AI response
        try:
            # Prepare the input
            input_text = question + tokenizer.eos_token
            input_ids = tokenizer.encode(input_text, return_tensors='pt')
            
            # Generate response
            output = model.generate(
                input_ids,
                max_length=1000,
                pad_token_id=tokenizer.eos_token_id,
                no_repeat_ngram_size=3,
                do_sample=True,
                top_k=100,
                top_p=0.7,
                temperature=0.8
            )
            
            # Decode the response
            response = tokenizer.decode(output[:, input_ids.shape[-1]:][0], skip_special_tokens=True)
            
            ai_response = {
                "answer": response,
                "sources": [document.original_filename] if document else []
            }
            
        except Exception as e:
            app.logger.error(f"AI generation error: {str(e)}")
            ai_response = {
                "answer": "I encountered an error processing your request. Please try again.",
                "sources": [document.original_filename] if document else []
            }
        
        # Save to chat history
        new_chat = ChatHistory(
            user_id=current_user.id,
            document_id=document.id if document else None,
            user_message=question,
            ai_response=ai_response['answer'],
            is_summary=False
        )
        db.session.add(new_chat)
        db.session.commit()
        
        return jsonify(ai_response)
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Ask question error: {str(e)}")
        return jsonify({"error": "Server error processing your question"}), 500

if __name__ == '__main__':
    app.run(debug=True)