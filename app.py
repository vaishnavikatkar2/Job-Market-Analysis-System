from functools import wraps
from decimal import Decimal, InvalidOperation
import csv, io, os

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for, make_response
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('FLASK_SECRET_KEY', 'change-this-secret-before-use'),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
CSRFProtect(app)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'job_market_db'),
}
STATUSES = ['Submitted', 'Under Review', 'Shortlisted', 'Rejected', 'Hired']

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

def fetch_all(query, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close(); conn.close()

def fetch_one(query, params=()):
    rows = fetch_all(query, params)
    return rows[0] if rows else None

def execute(query, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close(); conn.close()

def init_db():
    """Create app-specific tables; existing COMPANY/JOB/SKILL tables are preserved."""
    conn = get_connection(); cur = conn.cursor()
    statements = [
    """CREATE TABLE IF NOT EXISTS users (
       user_id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL,
       email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
       role ENUM('admin','user') NOT NULL DEFAULT 'user', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS job_applications (
       application_id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, job_id INT NOT NULL,
       cover_note TEXT, status ENUM('Submitted','Under Review','Shortlisted','Rejected','Hired') NOT NULL DEFAULT 'Submitted',
       applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE KEY unique_user_job (user_id,job_id),
       CONSTRAINT fk_application_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
       CONSTRAINT fk_application_job FOREIGN KEY (job_id) REFERENCES JOB(job_id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS saved_jobs (
       saved_id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, job_id INT NOT NULL,
       saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE KEY unique_saved_job (user_id,job_id),
       CONSTRAINT fk_saved_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
       CONSTRAINT fk_saved_job FOREIGN KEY (job_id) REFERENCES JOB(job_id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS user_profiles (
       user_id INT PRIMARY KEY, phone VARCHAR(30), headline VARCHAR(180), skills TEXT, bio TEXT,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
       CONSTRAINT fk_profile_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE)"""
    ]
    try:
        for sql in statements: cur.execute(sql)
        admin_email = os.getenv('ADMIN_EMAIL', '').strip().lower()
        admin_password = os.getenv('ADMIN_PASSWORD', '')
        if admin_email and admin_password:
            cur.execute('SELECT user_id FROM users WHERE email=%s', (admin_email,))
            if not cur.fetchone():
                cur.execute("INSERT INTO users(name,email,password_hash,role) VALUES(%s,%s,%s,'admin')",
                            ('Portal Administrator', admin_email, generate_password_hash(admin_password)))
        conn.commit()
    finally:
        cur.close(); conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please sign in to continue.', 'warning')
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please sign in first.', 'warning'); return redirect(url_for('login'))
        if session.get('role') != 'admin': abort(403)
        return fn(*args, **kwargs)
    return wrapper

def get_job(job_id):
    return fetch_one("""SELECT j.job_id,j.job_title,j.location,j.salary,j.company_id,c.company_name,c.industry,
      COALESCE(GROUP_CONCAT(DISTINCT s.skill_name ORDER BY s.skill_name SEPARATOR ', '),'') AS skills
      FROM JOB j JOIN COMPANY c ON c.company_id=j.company_id LEFT JOIN SKILL s ON s.job_id=j.job_id
      WHERE j.job_id=%s GROUP BY j.job_id,j.job_title,j.location,j.salary,j.company_id,c.company_name,c.industry""",(job_id,))

def parse_job_form():
    title=request.form.get('job_title','').strip(); location=request.form.get('location','').strip()
    company_raw=request.form.get('company_id','').strip(); salary_raw=request.form.get('salary','').strip()
    skills=list(dict.fromkeys(x.strip()[:100] for x in request.form.get('skills','').split(',') if x.strip()))
    if not title or not location or not company_raw or not salary_raw: raise ValueError('Title, company, location and salary are required.')
    try:
        company_id=int(company_raw); salary=Decimal(salary_raw)
        if salary < 0 or not salary.is_finite(): raise ValueError
    except (ValueError, InvalidOperation): raise ValueError('Enter a valid company and non-negative salary.')
    if not fetch_one('SELECT company_id FROM COMPANY WHERE company_id=%s',(company_id,)): raise ValueError('Choose a valid company.')
    return title[:150],company_id,location[:150],salary,skills

def replace_skills(cur, job_id, skills):
    cur.execute('DELETE FROM SKILL WHERE job_id=%s',(job_id,))
    cur.execute('SELECT COALESCE(MAX(skill_id),0) FROM SKILL'); next_id=int(cur.fetchone()[0])+1
    for skill in skills:
        cur.execute('INSERT INTO SKILL(skill_id,job_id,skill_name) VALUES(%s,%s,%s)',(next_id,job_id,skill)); next_id+=1

@app.context_processor
def inject_globals(): return {'current_year': __import__('datetime').datetime.now().year}

@app.route('/')
def index():
    if not session.get('user_id'): return redirect(url_for('login'))
    return redirect(url_for('admin_dashboard' if session.get('role')=='admin' else 'jobs'))

@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        if not name or not email or len(password)<10: flash('Enter your name/email and a password of at least 10 characters.','danger')
        else:
            try:
                execute("INSERT INTO users(name,email,password_hash,role) VALUES(%s,%s,%s,'user')",(name[:100],email,generate_password_hash(password)))
                flash('Account created. Sign in to continue.','success'); return redirect(url_for('login'))
            except mysql.connector.IntegrityError: flash('That email address is already registered.','danger')
    return render_template('register.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
        user=fetch_one('SELECT user_id,name,email,password_hash,role FROM users WHERE email=%s',(email,))
        if user and check_password_hash(user['password_hash'],password):
            session.clear(); session['user_id']=user['user_id']; session['name']=user['name']; session['role']=user['role']
            target='admin_dashboard' if user['role']=='admin' else 'jobs'
            return redirect(url_for(target))
        flash('Invalid email or password.','danger')
    return render_template('login.html')

@app.post('/logout')
@login_required
def logout(): session.clear(); flash('You have signed out.','info'); return redirect(url_for('login'))

@app.route('/jobs')
@login_required
def jobs():
    q=request.args.get('q','').strip(); location=request.args.get('location','').strip(); industry=request.args.get('industry','').strip()
    min_salary=request.args.get('min_salary','').strip(); max_salary=request.args.get('max_salary','').strip(); skill=request.args.get('skill','').strip()
    sort=request.args.get('sort','newest'); page=max(1,request.args.get('page',1,type=int)); per_page=9
    where=['1=1']; params=[]
    if q: where.append('(j.job_title LIKE %s OR c.company_name LIKE %s OR c.industry LIKE %s)'); params += [f'%{q}%']*3
    if location: where.append('j.location LIKE %s'); params.append(f'%{location}%')
    if industry: where.append('c.industry=%s'); params.append(industry)
    if skill: where.append('EXISTS (SELECT 1 FROM SKILL sx WHERE sx.job_id=j.job_id AND sx.skill_name LIKE %s)'); params.append(f'%{skill}%')
    for val,op in [(min_salary,'>='),(max_salary,'<=')]:
        if val:
            try: params.append(Decimal(val)); where.append(f'j.salary {op} %s')
            except InvalidOperation: flash('Salary filters must be numeric.','warning')
    order={'newest':'j.job_id DESC','salary_high':'j.salary DESC','salary_low':'j.salary ASC','title':'j.job_title ASC'}.get(sort,'j.job_id DESC')
    clause=' AND '.join(where)
    total=fetch_one(f'SELECT COUNT(DISTINCT j.job_id) AS n FROM JOB j JOIN COMPANY c ON c.company_id=j.company_id LEFT JOIN SKILL s ON s.job_id=j.job_id WHERE {clause}',tuple(params))['n']
    pages=max(1,(total+per_page-1)//per_page); page=min(page,pages)
    rows=fetch_all(f"""SELECT j.job_id,j.job_title,j.location,j.salary,c.company_name,c.industry,
      COALESCE(GROUP_CONCAT(DISTINCT s.skill_name ORDER BY s.skill_name SEPARATOR ', '),'') AS skills,
      EXISTS(SELECT 1 FROM saved_jobs sj WHERE sj.job_id=j.job_id AND sj.user_id=%s) AS is_saved,
      EXISTS(SELECT 1 FROM job_applications ja WHERE ja.job_id=j.job_id AND ja.user_id=%s) AS has_applied
      FROM JOB j JOIN COMPANY c ON c.company_id=j.company_id LEFT JOIN SKILL s ON s.job_id=j.job_id
      WHERE {clause} GROUP BY j.job_id,j.job_title,j.location,j.salary,c.company_name,c.industry
      ORDER BY {order} LIMIT %s OFFSET %s""",(session['user_id'],session['user_id'],*params,per_page,(page-1)*per_page))
    industries=fetch_all('SELECT DISTINCT industry FROM COMPANY WHERE industry IS NOT NULL AND industry<>\'\' ORDER BY industry')
    return render_template('jobs.html',jobs=rows,q=q,location=location,industry=industry,min_salary=min_salary,max_salary=max_salary,skill=skill,sort=sort,industries=industries,page=page,pages=pages,total=total)

@app.route('/jobs/<int:job_id>')
@login_required
def job_detail(job_id):
    job=get_job(job_id)
    if not job: abort(404)
    applied=bool(fetch_one('SELECT application_id FROM job_applications WHERE user_id=%s AND job_id=%s',(session['user_id'],job_id)))
    saved=bool(fetch_one('SELECT saved_id FROM saved_jobs WHERE user_id=%s AND job_id=%s',(session['user_id'],job_id)))
    return render_template('job_detail.html',job=job,applied=applied,saved=saved)

@app.post('/jobs/<int:job_id>/save')
@login_required
def toggle_save(job_id):
    if not get_job(job_id): abort(404)
    existing=fetch_one('SELECT saved_id FROM saved_jobs WHERE user_id=%s AND job_id=%s',(session['user_id'],job_id))
    if existing: execute('DELETE FROM saved_jobs WHERE saved_id=%s',(existing['saved_id'],)); flash('Job removed from saved list.','info')
    else: execute('INSERT IGNORE INTO saved_jobs(user_id,job_id) VALUES(%s,%s)',(session['user_id'],job_id)); flash('Job saved for later.','success')
    return redirect(request.referrer or url_for('jobs'))

@app.post('/jobs/<int:job_id>/apply')
@login_required
def apply_job(job_id):
    if not get_job(job_id): abort(404)
    note=request.form.get('cover_note','').strip()[:4000]
    try:
        execute('INSERT INTO job_applications(user_id,job_id,cover_note) VALUES(%s,%s,%s)',(session['user_id'],job_id,note))
        flash('Application submitted successfully.','success')
    except mysql.connector.IntegrityError: flash('You have already applied for this job.','warning')
    return redirect(url_for('my_applications'))

@app.route('/my-applications')
@login_required
def my_applications():
    rows=fetch_all("""SELECT a.application_id,a.status,a.applied_at,a.cover_note,j.job_id,j.job_title,j.location,j.salary,c.company_name
      FROM job_applications a JOIN JOB j ON j.job_id=a.job_id JOIN COMPANY c ON c.company_id=j.company_id
      WHERE a.user_id=%s ORDER BY a.applied_at DESC""",(session['user_id'],))
    return render_template('my_applications.html',applications=rows)

@app.route('/saved-jobs')
@login_required
def saved_jobs():
    rows=fetch_all("""SELECT j.job_id,j.job_title,j.location,j.salary,c.company_name,c.industry
      FROM saved_jobs s JOIN JOB j ON j.job_id=s.job_id JOIN COMPANY c ON c.company_id=j.company_id
      WHERE s.user_id=%s ORDER BY s.saved_at DESC""",(session['user_id'],))
    return render_template('saved_jobs.html',jobs=rows)

@app.route('/profile',methods=['GET','POST'])
@login_required
def profile():
    if request.method=='POST':
        name=request.form.get('name','').strip()[:100]; email=request.form.get('email','').strip().lower()
        phone=request.form.get('phone','').strip()[:30]; headline=request.form.get('headline','').strip()[:180]
        skills=request.form.get('skills','').strip()[:2000]; bio=request.form.get('bio','').strip()[:4000]
        if not name or not email: flash('Name and email are required.','danger')
        else:
            conn=get_connection(); cur=conn.cursor()
            try:
                cur.execute('UPDATE users SET name=%s,email=%s WHERE user_id=%s',(name,email,session['user_id']))
                cur.execute("""INSERT INTO user_profiles(user_id,phone,headline,skills,bio) VALUES(%s,%s,%s,%s,%s)
                  ON DUPLICATE KEY UPDATE phone=VALUES(phone),headline=VALUES(headline),skills=VALUES(skills),bio=VALUES(bio)""",(session['user_id'],phone,headline,skills,bio))
                conn.commit(); session['name']=name; flash('Profile updated.','success')
            except mysql.connector.IntegrityError: conn.rollback(); flash('That email is already in use.','danger')
            finally: cur.close(); conn.close()
            return redirect(url_for('profile'))
    user=fetch_one("""SELECT u.name,u.email,COALESCE(p.phone,'') phone,COALESCE(p.headline,'') headline,
      COALESCE(p.skills,'') skills,COALESCE(p.bio,'') bio FROM users u LEFT JOIN user_profiles p ON p.user_id=u.user_id WHERE u.user_id=%s""",(session['user_id'],))
    return render_template('profile.html',user=user)

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats={
      'jobs':fetch_one('SELECT COUNT(*) n FROM JOB')['n'],
      'companies':fetch_one('SELECT COUNT(*) n FROM COMPANY')['n'],
      'users':fetch_one("SELECT COUNT(*) n FROM users WHERE role='user'")['n'],
      'applications':fetch_one('SELECT COUNT(*) n FROM job_applications')['n'],
    }
    by_industry=fetch_all("""SELECT COALESCE(c.industry,'Other') label,COUNT(*) value FROM JOB j JOIN COMPANY c ON c.company_id=j.company_id GROUP BY c.industry ORDER BY value DESC LIMIT 8""")
    by_location=fetch_all('SELECT location label,COUNT(*) value FROM JOB GROUP BY location ORDER BY value DESC LIMIT 8')
    salary=fetch_one('SELECT COALESCE(AVG(salary),0) avg_salary,COALESCE(MAX(salary),0) max_salary FROM JOB')
    recent=fetch_all("""SELECT j.job_id,j.job_title,j.location,j.salary,c.company_name FROM JOB j JOIN COMPANY c ON c.company_id=j.company_id ORDER BY j.job_id DESC LIMIT 8""")
    return render_template('admin_dashboard.html',stats=stats,by_industry=by_industry,by_location=by_location,salary=salary,recent=recent)

@app.route('/admin/jobs')
@admin_required
def admin_jobs():
    q=request.args.get('q','').strip()
    rows=fetch_all("""SELECT j.job_id,j.job_title,j.location,j.salary,c.company_name,c.industry FROM JOB j JOIN COMPANY c ON c.company_id=j.company_id
      WHERE j.job_title LIKE %s OR c.company_name LIKE %s ORDER BY j.job_id DESC""",(f'%{q}%',f'%{q}%'))
    return render_template('admin_jobs.html',jobs=rows,q=q)

@app.route('/admin/jobs/new',methods=['GET','POST'])
@admin_required
def add_job():
    companies=fetch_all('SELECT company_id,company_name FROM COMPANY ORDER BY company_name')
    if not companies: flash('Add a company in MySQL Workbench before creating a job.','warning')
    if request.method=='POST':
        try:
            title,company_id,location,salary,skills=parse_job_form()
            conn=get_connection(); cur=conn.cursor()
            try:
                cur.execute('SELECT COALESCE(MAX(job_id),0)+1 FROM JOB'); job_id=int(cur.fetchone()[0])
                cur.execute('INSERT INTO JOB(job_id,company_id,job_title,location,salary) VALUES(%s,%s,%s,%s,%s)',(job_id,company_id,title,location,salary))
                replace_skills(cur,job_id,skills); conn.commit()
            except Exception: conn.rollback(); raise
            finally: cur.close(); conn.close()
            flash('Job created.','success'); return redirect(url_for('admin_jobs'))
        except ValueError as e: flash(str(e),'danger')
    return render_template('job_form.html',job=None,companies=companies)

@app.route('/admin/jobs/<int:job_id>/edit',methods=['GET','POST'])
@admin_required
def edit_job(job_id):
    job=get_job(job_id)
    if not job: abort(404)
    companies=fetch_all('SELECT company_id,company_name FROM COMPANY ORDER BY company_name')
    if request.method=='POST':
        try:
            title,company_id,location,salary,skills=parse_job_form()
            conn=get_connection(); cur=conn.cursor()
            try:
                cur.execute('UPDATE JOB SET company_id=%s,job_title=%s,location=%s,salary=%s WHERE job_id=%s',(company_id,title,location,salary,job_id))
                replace_skills(cur,job_id,skills); conn.commit()
            except Exception: conn.rollback(); raise
            finally: cur.close(); conn.close()
            flash('Job updated.','success'); return redirect(url_for('admin_jobs'))
        except ValueError as e: flash(str(e),'danger')
    return render_template('job_form.html',job=job,companies=companies)

@app.post('/admin/jobs/<int:job_id>/delete')
@admin_required
def delete_job(job_id):
    if not get_job(job_id): abort(404)
    conn=get_connection(); cur=conn.cursor()
    try:
        cur.execute('DELETE FROM SKILL WHERE job_id=%s',(job_id,)); cur.execute('DELETE FROM JOB WHERE job_id=%s',(job_id,)); conn.commit()
        flash('Job deleted.','success')
    except Exception: conn.rollback(); raise
    finally: cur.close(); conn.close()
    return redirect(url_for('admin_jobs'))

@app.route('/admin/applications')
@admin_required
def admin_applications():
    status=request.args.get('status','').strip(); where='WHERE a.status=%s' if status in STATUSES else ''; params=(status,) if where else ()
    rows=fetch_all(f"""SELECT a.application_id,a.status,a.applied_at,a.cover_note,u.name applicant,u.email,j.job_title,c.company_name
      FROM job_applications a JOIN users u ON u.user_id=a.user_id JOIN JOB j ON j.job_id=a.job_id JOIN COMPANY c ON c.company_id=j.company_id
      {where} ORDER BY a.applied_at DESC""",params)
    return render_template('admin_applications.html',applications=rows,status=status,statuses=STATUSES)

@app.post('/admin/applications/<int:application_id>/status')
@admin_required
def update_application(application_id):
    status=request.form.get('status','')
    if status not in STATUSES: abort(400)
    execute('UPDATE job_applications SET status=%s WHERE application_id=%s',(status,application_id))
    flash('Application status updated.','success'); return redirect(url_for('admin_applications'))

@app.route('/admin/export/jobs.csv')
@admin_required
def export_jobs():
    rows=fetch_all("""SELECT j.job_id,j.job_title,c.company_name,c.industry,j.location,j.salary,
      COALESCE(GROUP_CONCAT(DISTINCT s.skill_name SEPARATOR ', '),'') skills FROM JOB j JOIN COMPANY c ON c.company_id=j.company_id
      LEFT JOIN SKILL s ON s.job_id=j.job_id GROUP BY j.job_id,j.job_title,c.company_name,c.industry,j.location,j.salary ORDER BY j.job_id""")
    stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=['job_id','job_title','company_name','industry','location','salary','skills'])
    writer.writeheader(); writer.writerows(rows)
    response=make_response(stream.getvalue()); response.headers['Content-Type']='text/csv; charset=utf-8'; response.headers['Content-Disposition']='attachment; filename=job_market_export.csv'
    return response

@app.errorhandler(403)
def forbidden(_): return render_template('error.html',code=403,message='You do not have permission to access this page.'),403
@app.errorhandler(404)
def not_found(_): return render_template('error.html',code=404,message='The page or job you requested was not found.'),404

if __name__=='__main__':
    try:
        init_db()
        print('Database tables checked. Open http://127.0.0.1:5000')
    except mysql.connector.Error as exc:
        raise SystemExit(f'MySQL setup failed: {exc}\nCheck that MySQL is running and .env credentials are correct.')
    app.run(debug=os.getenv('FLASK_DEBUG','false').lower()=='true')
