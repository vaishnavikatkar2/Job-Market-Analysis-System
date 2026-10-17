/* =====================================================================
   PROJECT: TalentScope - Job Market Intelligence & Recruitment Portal
   DATABASE: job_market_db
   PURPOSE: DBMS query reference for project demonstration/viva

   IMPORTANT:
   - This file does NOT DROP any database or table.
   - COMPANY, JOB and SKILL are the existing project tables.
   - The application creates users, job_applications, saved_jobs and
     user_profiles if they do not already exist.
   - Run the CREATE TABLE statements only if those tables do not exist;
     CREATE TABLE IF NOT EXISTS is safe for existing tables.
   ===================================================================== */

CREATE DATABASE IF NOT EXISTS job_market_db;
USE job_market_db;

/* ---------------------------------------------------------------------
   SECTION 1: CORE TABLES (existing schema reference)
   These definitions document the expected structure. If the tables
   already exist, MySQL leaves them unchanged.
   --------------------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS COMPANY (
    company_id INT PRIMARY KEY,
    company_name VARCHAR(150) NOT NULL,
    industry VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS JOB (
    job_id INT PRIMARY KEY,
    company_id INT NOT NULL,
    job_title VARCHAR(150) NOT NULL,
    location VARCHAR(100) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    CONSTRAINT fk_job_company
        FOREIGN KEY (company_id) REFERENCES COMPANY(company_id)
);

CREATE TABLE IF NOT EXISTS SKILL (
    skill_id INT PRIMARY KEY,
    job_id INT NOT NULL,
    skill_name VARCHAR(100) NOT NULL,
    CONSTRAINT fk_skill_job
        FOREIGN KEY (job_id) REFERENCES JOB(job_id)
        ON DELETE CASCADE
);

/* ---------------------------------------------------------------------
   SECTION 2: ADDITIONAL TABLES USED BY THE ADVANCED WEB APPLICATION
   --------------------------------------------------------------------- */
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin','user') NOT NULL DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_applications (
    application_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    job_id INT NOT NULL,
    cover_note TEXT,
    status ENUM('Submitted','Under Review','Shortlisted','Rejected','Hired')
        NOT NULL DEFAULT 'Submitted',
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_job (user_id, job_id),
    CONSTRAINT fk_application_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_application_job FOREIGN KEY (job_id)
        REFERENCES JOB(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS saved_jobs (
    saved_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    job_id INT NOT NULL,
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_saved_job (user_id, job_id),
    CONSTRAINT fk_saved_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_saved_job FOREIGN KEY (job_id)
        REFERENCES JOB(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INT PRIMARY KEY,
    phone VARCHAR(30),
    headline VARCHAR(180),
    skills TEXT,
    bio TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_profile_user FOREIGN KEY (user_id)
        REFERENCES users(user_id) ON DELETE CASCADE
);

/* ---------------------------------------------------------------------
   SECTION 3: READ / RETRIEVE OPERATIONS (SELECT)
   --------------------------------------------------------------------- */

-- Q1. Display all jobs.
SELECT * FROM JOB;

-- Q2. Display jobs with the company name and industry (INNER JOIN).
SELECT j.job_id, j.job_title, c.company_name, c.industry,
       j.location, j.salary
FROM JOB AS j
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
ORDER BY j.job_id DESC;

-- Q3. Display each job and its skills (LEFT JOIN; jobs without skills remain visible).
SELECT j.job_id, j.job_title, c.company_name,
       GROUP_CONCAT(DISTINCT s.skill_name ORDER BY s.skill_name SEPARATOR ', ') AS skills
FROM JOB AS j
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
LEFT JOIN SKILL AS s ON s.job_id = j.job_id
GROUP BY j.job_id, j.job_title, c.company_name
ORDER BY j.job_id;

-- Q4. Search job title or company name (LIKE pattern matching).
SELECT j.job_id, j.job_title, c.company_name, j.location, j.salary
FROM JOB AS j
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
WHERE j.job_title LIKE '%Developer%'
   OR c.company_name LIKE '%TCS%';

-- Q5. Filter by location.
SELECT j.job_title, c.company_name, j.location, j.salary
FROM JOB AS j
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
WHERE j.location LIKE '%Pune%';

-- Q6. Filter jobs by minimum and maximum salary.
SELECT job_title, location, salary
FROM JOB
WHERE salary BETWEEN 400000 AND 1000000
ORDER BY salary DESC;

-- Q7. Filter jobs by a particular skill.
SELECT DISTINCT j.job_id, j.job_title, c.company_name, j.location, j.salary
FROM JOB AS j
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
INNER JOIN SKILL AS s ON s.job_id = j.job_id
WHERE s.skill_name LIKE '%Python%';

-- Q8. List distinct industries for the search filter.
SELECT DISTINCT industry
FROM COMPANY
WHERE industry IS NOT NULL AND industry <> ''
ORDER BY industry;

/* ---------------------------------------------------------------------
   SECTION 4: AGGREGATE FUNCTIONS AND ANALYTICS
   --------------------------------------------------------------------- */

-- Q9. Count all jobs, companies, registered users and applications.
SELECT (SELECT COUNT(*) FROM JOB) AS total_jobs,
       (SELECT COUNT(*) FROM COMPANY) AS total_companies,
       (SELECT COUNT(*) FROM users WHERE role = 'user') AS total_users,
       (SELECT COUNT(*) FROM job_applications) AS total_applications;

-- Q10. Calculate average and highest salary.
SELECT AVG(salary) AS average_salary,
       MAX(salary) AS highest_salary,
       MIN(salary) AS lowest_salary
FROM JOB;

-- Q11. Count jobs by industry (GROUP BY and ORDER BY).
SELECT COALESCE(c.industry, 'Other') AS industry,
       COUNT(*) AS number_of_jobs
FROM JOB AS j
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
GROUP BY c.industry
ORDER BY number_of_jobs DESC;

-- Q12. Count jobs by location.
SELECT location, COUNT(*) AS number_of_jobs
FROM JOB
GROUP BY location
ORDER BY number_of_jobs DESC;

-- Q13. Show industries with at least two job postings (HAVING).
SELECT c.industry, COUNT(*) AS number_of_jobs
FROM JOB AS j
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
GROUP BY c.industry
HAVING COUNT(*) >= 2
ORDER BY number_of_jobs DESC;

-- Q14. Find jobs that pay more than the average salary (subquery).
SELECT job_title, location, salary
FROM JOB
WHERE salary > (SELECT AVG(salary) FROM JOB)
ORDER BY salary DESC;

-- Q15. Skill demand: count how many job postings request each skill.
SELECT skill_name, COUNT(DISTINCT job_id) AS jobs_requiring_skill
FROM SKILL
GROUP BY skill_name
ORDER BY jobs_requiring_skill DESC, skill_name;

/* ---------------------------------------------------------------------
   SECTION 5: USER / APPLICATION / SAVED-JOB QUERIES
   --------------------------------------------------------------------- */

-- Q16. Find a user's applications with job and company details.
-- Replace 1 with the required user_id.
SELECT a.application_id, a.status, a.applied_at, a.cover_note,
       j.job_title, c.company_name, j.location, j.salary
FROM job_applications AS a
INNER JOIN JOB AS j ON j.job_id = a.job_id
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
WHERE a.user_id = 1
ORDER BY a.applied_at DESC;

-- Q17. Find applicants for each job (admin application review).
SELECT a.application_id, a.status, a.applied_at,
       u.name AS applicant_name, u.email,
       j.job_title, c.company_name
FROM job_applications AS a
INNER JOIN users AS u ON u.user_id = a.user_id
INNER JOIN JOB AS j ON j.job_id = a.job_id
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
ORDER BY a.applied_at DESC;

-- Q18. List saved jobs for one user. Replace 1 with the required user_id.
SELECT j.job_id, j.job_title, c.company_name, j.location, j.salary, s.saved_at
FROM saved_jobs AS s
INNER JOIN JOB AS j ON j.job_id = s.job_id
INNER JOIN COMPANY AS c ON c.company_id = j.company_id
WHERE s.user_id = 1
ORDER BY s.saved_at DESC;

-- Q19. Count applications by status.
SELECT status, COUNT(*) AS application_count
FROM job_applications
GROUP BY status
ORDER BY application_count DESC;

/* ---------------------------------------------------------------------
   SECTION 6: CREATE / INSERT / UPDATE / DELETE EXAMPLES (CRUD)
   These examples are comments so they do not modify data accidentally.
   The web application performs equivalent operations with parameterized
   queries and validates input before executing them.
   --------------------------------------------------------------------- */

-- CREATE / INSERT: add a job. Use a valid company_id and an unused job_id.
-- INSERT INTO JOB (job_id, company_id, job_title, location, salary)
-- VALUES (101, 1, 'Backend Developer', 'Pune', 750000);

-- INSERT a skill for an existing job. Use an unused skill_id.
-- INSERT INTO SKILL (skill_id, job_id, skill_name)
-- VALUES (501, 101, 'Python');

-- UPDATE: edit a job's details.
-- UPDATE JOB
-- SET job_title = 'Senior Backend Developer', location = 'Mumbai', salary = 950000
-- WHERE job_id = 101;

-- UPDATE: change an application status (use a valid application_id/status).
-- UPDATE job_applications
-- SET status = 'Under Review'
-- WHERE application_id = 1;

-- DELETE: remove skills before deleting a job if FK cascade is not configured
-- on the existing SKILL table. The web app deletes related skills first.
-- DELETE FROM SKILL WHERE job_id = 101;
-- DELETE FROM JOB WHERE job_id = 101;

-- DELETE: unsave a job for a user.
-- DELETE FROM saved_jobs WHERE user_id = 1 AND job_id = 101;

/* ---------------------------------------------------------------------
   SECTION 7: CONSTRAINTS / RELATIONSHIPS TO EXPLAIN
   --------------------------------------------------------------------- */
-- PRIMARY KEY: uniquely identifies each row (company_id, job_id, skill_id, etc.).
-- FOREIGN KEY: JOB.company_id -> COMPANY.company_id; SKILL.job_id -> JOB.job_id.
-- UNIQUE: users.email; one application per user/job; one saved entry per user/job.
-- NOT NULL: required fields such as names, titles, locations and salaries.
-- ENUM: restricts role and application status to supported values.
-- ON DELETE CASCADE: removes related profile/application/saved-job rows when
-- their referenced user or job is deleted, where that FK is defined with cascade.

-- End of query reference. No trigger or stored procedure is created by this file.
