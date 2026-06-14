from flask import app, request, jsonify
import dbconnect
import bcrypt
from datetime import datetime, timedelta
import pytz
from decimal import Decimal
import logging
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import traceback

#import pymysql

# for Pusher data stream
import pusher

# for google FCM
import google.auth.transport.requests

# for AWS Textract and Bedrock
from summarizer import extract_text_from_textract, summarize_text_with_bedrock

import boto3
import json

from config import settings

sqs = boto3.client("sqs", region_name=settings.sqs_region)
EDMS_INGESTION_QUEUE_URL = settings.edms_ingestion_queue_url

logger = logging.getLogger(__name__)

def send_edms_ingestion_message(org_code, wo_number, wo_code=None):
    message = {
        "org_code": org_code,
        "wo_number": wo_number,
        "wo_code": wo_code
    }

    sqs.send_message(
        QueueUrl=EDMS_INGESTION_QUEUE_URL,
        MessageBody=json.dumps(message)
    )

# Configure Pusher
pusher_client = pusher.Pusher(
    app_id=settings.pusher_app_id,
    key=settings.pusher_key,
    secret=settings.pusher_secret,
    cluster=settings.pusher_cluster,
    ssl=True
)


#--- get server date & time ----#
def timezone2():
    
    try:
        tz = pytz.timezone('UTC')
        now = datetime.now(tz) + timedelta(hours = 8)

        formatted_datetime = now.strftime('%Y-%m-%d %H:%M:%S') 
        
        return formatted_datetime
        #app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
        #return jsonify({"results" : formatted_datetime})
        
    except Exception as e:
        return(str(e))        
    

#--- get Philippine server date & time ----#
def ph_datetime():
    try:
        tz = pytz.timezone('UTC')
        now = datetime.now(tz) + timedelta(hours=8)  # PH timezone
        return now
    except Exception as e:
        raise e
    

# WAC send email facility for the approval notification
def wac_send_email_notification(email_address, reference_id, subject_title, action_title):
    
    try:    
        sender_email = settings.gmail_sender
        receiver_email = email_address.strip()  # Strip any whitespace
        password = settings.gmail_app_password
        
        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", receiver_email):
            raise ValueError(f"Invalid email address: {receiver_email}")
        
        #logger.info(f"Sending email to: {receiver_email}")

        subject = subject_title
        body = (
            f"Hello,\n\n"
            f"This is to inform you that {reference_id} has been routed to you for {action_title}\n\n"
            f"Please review the details and take the appropriate action through the system at your earliest convenience.\n\n"
            f"Thank you,\n"
            f"Work and Cost Management System\n\n"
            f"Automated Notification - Please do not reply to this email."
        )

        # Set up the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to the email server and send the email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        #logger.info(f"Email notification sent to {receiver_email}.")
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")


# WAC send email facility for the work order has been approved notification
def wac_approved_send_email_notification(email_address, reference_id, subject_title, action_title):
    
    try:    
        sender_email = settings.gmail_sender
        receiver_email = email_address.strip()  # Strip any whitespace
        password = settings.gmail_app_password
        
        # Validate email format
        if not re.match(r"[^@]+@[^@]+\.[^@]+", receiver_email):
            raise ValueError(f"Invalid email address: {receiver_email}")
        
        #logger.info(f"Sending email to: {receiver_email}")

        subject = subject_title
        body = (
            f"Hello,\n\n"
            f"{reference_id} has been {action_title}.\n\n"
            f"Please Please refer to the system for further details.\n\n"
            f"Thank you,\n"
            f"Work and Cost Management System\n\n"
            f"Automated Notification - Please do not reply to this email."
        )

        # Set up the email message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect to the email server and send the email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())

        #logger.info(f"Email notification sent to {receiver_email}.")
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")


#-- Generate new number for material CUs, MAT series
def get_next_cu_code(series_name):
    conn = dbconnect.getConnection()
    cur = conn.cursor()
        
    # Lock the table to avoid race condition (if needed)
    cur.execute("SELECT last_number FROM cu_code_series FOR UPDATE")
    row = cur.fetchone()

    last_number = int(row['last_number'])
    next_number = last_number + 1
        
    # Update the counter
    cur.execute("UPDATE cu_code_series SET last_number = %s", (next_number,))
    conn.commit()
    conn.close()

    return f"{series_name}{str(next_number).zfill(7)}"


    #-- Generate new number for cu category code
def get_next_cu_category_code():
    conn = dbconnect.getConnection()
    cur = conn.cursor()
        
    # Lock the table to avoid race condition (if needed)
    cur.execute("SELECT last_number FROM cu_category_code_series FOR UPDATE")
    row = cur.fetchone()

    last_number = int(row['last_number'])
    next_number = last_number + 1
        
    # Update the counter
    cur.execute("UPDATE cu_category_code_series SET last_number = %s", (next_number,))
    conn.commit()
    conn.close()

    return f"CAT{str(next_number).zfill(7)}"


#-- Generate new number for business unit code
def get_next_business_unit_code():
    conn = dbconnect.getConnection()
    cur = conn.cursor()
        
    # Lock the table to avoid race condition (if needed)
    cur.execute("SELECT last_number FROM business_unit_code_series FOR UPDATE")
    row = cur.fetchone()

    last_number = int(row['last_number'])
    next_number = last_number + 1
        
    # Update the counter
    cur.execute("UPDATE business_unit_code_series SET last_number = %s", (next_number,))
    conn.commit()
    conn.close()

    return f"BU{str(next_number).zfill(6)}"


def register_mutate_routes(app):
    #--- upload file to AWS S3 bucket----#
    @app.route('/uploadwacfile', methods=['POST'])
    def uploadwacfile():
        file = request.files['file']
        file_name = file.filename
        
        try:
            conn = dbconnect.getS3Connection()
            conn.upload_fileobj(file, 'vivant-wac-uat', file_name)
            
            # Get the URL of the uploaded file
            #url = f"https://policetrack-images.s3.ap-southeast-1.amazonaws.com/{file_name}"
            url = file_name
            
            result = {
                'url': url
            }
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "File uploadd successfully", "result": result}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new customer ----#
    @app.route('/postcustomer', methods=['POST'])
    def postcustomer():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            logger.info("new customer: ")
            logger.info(passed_data)
            
            hashed_pw = ""

            if passed_data.get("built_in_password"):
                raw_password = passed_data["built_in_password"]
                hashed_pw = hash_password(raw_password)
            
            # SQL for inserting record into customers
            sql1 = """INSERT INTO customers (firstname, middlename, lastname, email_address,  contact_number, street_address, city, province, company_name, org_code, created_datetime) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["firstname"], passed_data["middlename"], passed_data["lastname"], passed_data["email_address"],  passed_data["contact_number"], passed_data["street_address"], passed_data["city"], passed_data["province"], passed_data["company_name"], passed_data["org_code"], now)
            
            cur.execute(sql1, data1)
            
            # Get the newly created customer id
            customer_id = cur.lastrowid
            
            # SQL for inserting record into app_users
            sql1 = """INSERT INTO app_users (user, built_in, built_in_password, oauth, status, firstname, lastname, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["email_address"], passed_data["built_in"], hashed_pw, passed_data["oauth"], 1, passed_data["firstname"], passed_data["lastname"], passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # SQL for inserting record into app_user_roles
            #sql1 = """INSERT INTO app_user_roles (user, role, status, org_code) VALUES (%s, %s, %s, #%s)"""
            #data1 = (passed_data["email_address"], passed_data["role"], 1,  passed_data["org_code"])
            
            #cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Customer created successfully", "result": "created"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            logger.error(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new work request with planners ----#
    '''
    @app.route('/postworkrequest', methods=['POST'])
    def postworkrequest():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            new_wr_code = generate_next_wr_code()
            
            # SQL for inserting work request data
            sql1 = """INSERT INTO work_requests (firstname, middlename, lastname, email_address, customer_type, business_unit, project_location, proposal_deadline, job_start_date, job_end_date, project_desc, project_details, submitted_datetime, status, org_code, project_gid, wr_code, priority_level) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            data1 = (
                passed_data["firstname"],
                passed_data["middlename"],
                passed_data["lastname"],
                passed_data["email_address"],
                passed_data["customer_type"],
                passed_data["business_unit"],
                passed_data["project_location"],
                passed_data["proposal_deadline"],
                passed_data["job_start_date"],
                passed_data["job_end_date"],
                passed_data["project_desc"],
                passed_data["project_details"],
                now,
                passed_data["status"],
                passed_data["org_code"],
                passed_data["project_gid"],
                new_wr_code,
                passed_data["priority_level"]
            )
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            wr_id = cur.lastrowid
            
            # SQL for inserting requested services
            insert_services = """INSERT INTO requested_services (wr_id, service_id, detail_id, org_code) VALUES (%s, %s, %s, %s)"""
            
            # Process each parent and its children
            for parent in passed_data["services"]:
                parent_id = parent.get("parent_id")
                children = parent.get("children", [])

                # Insert the parent with no child if `children` is empty
                if not children:
                    cur.execute(insert_services, (wr_id, parent_id, 0, passed_data["org_code"]))

                # Insert each child
                for child in children:
                    child_id = child.get("child_id")
                    cur.execute(insert_services, (wr_id, parent_id, child_id, passed_data["org_code"]))
            
            # SQL for updating remarks
            update_remarks = """UPDATE requested_services SET remarks = %s WHERE service_id = %s AND detail_id = %s AND wr_id = %s"""

            # Process the remarks list
            for remark in passed_data["remarkslist"]:
                service_id = remark.get("service_id")
                detail_id = remark.get("detail_id")
                remarkdata = remark.get("remarks")

                cur.execute(update_remarks, (remarkdata, service_id, detail_id, wr_id))

            # --- NEW: save selected planners to work_order_team ---
            planners = passed_data.get("planners", [])

            insert_team = """
                INSERT INTO work_order_team
                (wo_number, user, role, assigned_datetime, org_code, wr_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """

            for planner in planners:
                if planner and str(planner).strip():
                    cur.execute(insert_team, (
                        None,
                        planner,
                        "planner",
                        now,
                        passed_data["org_code"],
                        wr_id
                    ))

            # SQL for inserting into status change logs
            sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (
                "Work Request",
                wr_id,
                "",
                passed_data["status"],
                passed_data["email_address"],
                "New work request",
                now,
                "Web App",
                passed_data["org_code"]
            )
            
            cur.execute(sql1, data1)

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Request created successfully", "result": wr_id}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    '''
    #--- save new work request with planners / approvers ----#
    @app.route('/postworkrequest', methods=['POST'])
    def postworkrequest():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            new_wr_code = generate_next_wr_code()

            # --- validation ---
            planners = passed_data.get("planners", [])
            valid_planners = [p for p in planners if str(p).strip()]

            pre_approver = passed_data.get("pre_approver", "")
            approver = passed_data.get("approver", "")

            if len(valid_planners) == 0:
                return jsonify({
                    "error": "At least one planner must be assigned to the work request."
                }), 400

            if not str(pre_approver).strip():
                return jsonify({
                    "error": "Pre-Approver is required."
                }), 400

            if not str(approver).strip():
                return jsonify({
                    "error": "Final Approver is required."
                }), 400
            
            # SQL for inserting work request data
            sql1 = """INSERT INTO work_requests (
                        firstname, middlename, lastname, email_address,
                        customer_type, business_unit, project_location,
                        proposal_deadline, job_start_date, job_end_date,
                        project_desc, project_details, submitted_datetime,
                        status, org_code, project_gid, wr_code, priority_level
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            data1 = (
                passed_data["firstname"],
                passed_data["middlename"],
                passed_data["lastname"],
                passed_data["email_address"],
                passed_data["customer_type"],
                passed_data["business_unit"],
                passed_data["project_location"],
                passed_data["proposal_deadline"],
                passed_data["job_start_date"],
                passed_data["job_end_date"],
                passed_data["project_desc"],
                passed_data["project_details"],
                now,
                passed_data["status"],
                passed_data["org_code"],
                passed_data["project_gid"],
                new_wr_code,
                passed_data["priority_level"]
            )
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            wr_id = cur.lastrowid
            
            # SQL for inserting requested services
            insert_services = """INSERT INTO requested_services (wr_id, service_id, detail_id, org_code)
                                VALUES (%s, %s, %s, %s)"""
            
            # Process each parent and its children
            for parent in passed_data["services"]:
                parent_id = parent.get("parent_id")
                children = parent.get("children", [])

                # Insert the parent with no child if `children` is empty
                if not children:
                    cur.execute(insert_services, (wr_id, parent_id, 0, passed_data["org_code"]))

                # Insert each child
                for child in children:
                    child_id = child.get("child_id")
                    cur.execute(insert_services, (wr_id, parent_id, child_id, passed_data["org_code"]))
            
            # SQL for updating remarks
            update_remarks = """UPDATE requested_services
                                SET remarks = %s
                                WHERE service_id = %s AND detail_id = %s AND wr_id = %s"""

            # Process the remarks list
            for remark in passed_data["remarkslist"]:
                service_id = remark.get("service_id")
                detail_id = remark.get("detail_id")
                remarkdata = remark.get("remarks")

                cur.execute(update_remarks, (remarkdata, service_id, detail_id, wr_id))

            # --- save selected planners / approvers to work_order_team ---
            insert_team = """
                INSERT INTO work_order_team
                (wo_number, user, role, assigned_datetime, org_code, wr_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """

            # planners
            for planner in valid_planners:
                cur.execute(insert_team, (
                    None,
                    planner,
                    "planner",
                    now,
                    passed_data["org_code"],
                    wr_id
                ))

            # pre-approver = team lead
            cur.execute(insert_team, (
                None,
                pre_approver,
                "team lead",
                now,
                passed_data["org_code"],
                wr_id
            ))

            # final approver = manager
            cur.execute(insert_team, (
                None,
                approver,
                "manager",
                now,
                passed_data["org_code"],
                wr_id
            ))

            # SQL for inserting into status change logs
            sql1 = """INSERT INTO status_changes
                        (txn_type, txn_reference, previous_status, new_status,
                        changed_by, change_reason, changed_on, source, org_code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (
                "Work Request",
                wr_id,
                "",
                passed_data["status"],
                passed_data["email_address"],
                "New work request",
                now,
                "Web App",
                passed_data["org_code"]
            )
            
            cur.execute(sql1, data1)

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Request created successfully", "result": wr_id}), 201
        
        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    

    #--- save work request changes ----#
    '''
    @app.route('/updateworkrequest', methods=['POST'])
    def updateworkrequest():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            wr_id = int(passed_data["wr_id"])
            planners = passed_data.get("planners", [])
            
            # --- validation: at least 1 planner required ---
            valid_planners = [p for p in planners if str(p).strip()]
            if len(valid_planners) == 0:
                return jsonify({
                    "error": "At least one planner must be assigned to the work request."
                }), 400
            
            now = timezone2()
            
            # SQL for updating work request data
            sql1 = """UPDATE work_requests 
                    SET firstname = %s, 
                        middlename = %s, 
                        lastname = %s, 
                        email_address = %s, 
                        customer_type = %s, 
                        business_unit = %s, 
                        project_location = %s, 
                        proposal_deadline = %s, 
                        job_start_date = %s, 
                        job_end_date = %s, 
                        project_desc = %s, 
                        project_details = %s, 
                        submitted_datetime = %s, 
                        status = %s, 
                        org_code = %s, 
                        project_gid = %s, 
                        priority_level = %s 
                    WHERE wr_id = %s"""
            
            data1 = (
                passed_data["firstname"],
                passed_data["middlename"],
                passed_data["lastname"],
                passed_data["email_address"],
                passed_data["customer_type"],
                passed_data["business_unit"],
                passed_data["project_location"],
                passed_data["proposal_deadline"],
                passed_data["job_start_date"],
                passed_data["job_end_date"],
                passed_data["project_desc"],
                passed_data["project_details"],
                now,
                passed_data["status"],
                passed_data["org_code"],
                passed_data["project_gid"],
                passed_data["priority_level"],
                wr_id
            )
            cur.execute(sql1, data1)
            
            
            # SQL for deleting requested services
            delete_services = """DELETE FROM requested_services WHERE wr_id = %s"""
            cur.execute(delete_services, (wr_id,))
            
            
            # SQL for inserting requested services
            insert_services = """INSERT INTO requested_services (wr_id, service_id, detail_id, org_code) VALUES (%s, %s, %s, %s)"""
            
            # Process each parent and its children
            for parent in passed_data["services"]:
                parent_id = parent.get("parent_id")
                children = parent.get("children", [])

                # Insert the parent with no child if `children` is empty
                if not children:
                    cur.execute(
                        insert_services,
                        (wr_id, parent_id, 0, passed_data["org_code"])
                    )

                # Insert each child
                for child in children:
                    child_id = child.get("child_id")
                    cur.execute(
                        insert_services,
                        (wr_id, parent_id, child_id, passed_data["org_code"])
                    )
            
            
            # SQL for updating remarks
            update_remarks = """UPDATE requested_services 
                                SET remarks = %s 
                                WHERE service_id = %s AND detail_id = %s AND wr_id = %s"""

            # Process the remarks list
            for remark in passed_data["remarkslist"]:
                service_id = remark.get("service_id")
                detail_id = remark.get("detail_id")
                remarkdata = remark.get("remarks")

                cur.execute(update_remarks, (remarkdata, service_id, detail_id, wr_id))
            
            
            # --- NEW: refresh planners in work_order_team ---
            delete_planners = """
                DELETE FROM work_order_team
                WHERE wr_id = %s
                AND org_code = %s
                AND role = %s
            """
            cur.execute(delete_planners, (wr_id, passed_data["org_code"], "planner"))
            
            insert_planner = """
                INSERT INTO work_order_team
                (wo_number, user, role, assigned_datetime, org_code, wr_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            for planner in valid_planners:
                cur.execute(
                    insert_planner,
                    (None, planner, "planner", now, passed_data["org_code"], wr_id)
                )
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Request changes saved successfully", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    '''
    #--- save work request changes ----#
    @app.route('/updateworkrequest', methods=['POST'])
    def updateworkrequest():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            wr_id = int(passed_data["wr_id"])
            planners = passed_data.get("planners", [])
            pre_approver = passed_data.get("pre_approver", "")
            approver = passed_data.get("approver", "")
            
            # --- validation ---
            valid_planners = [p for p in planners if str(p).strip()]
            if len(valid_planners) == 0:
                return jsonify({
                    "error": "At least one planner must be assigned to the work request."
                }), 400

            if not str(pre_approver).strip():
                return jsonify({
                    "error": "Pre-Approver is required."
                }), 400

            if not str(approver).strip():
                return jsonify({
                    "error": "Final Approver is required."
                }), 400
            
            now = timezone2()
            
            # SQL for updating work request data
            sql1 = """UPDATE work_requests 
                    SET firstname = %s, 
                        middlename = %s, 
                        lastname = %s, 
                        email_address = %s, 
                        customer_type = %s, 
                        business_unit = %s, 
                        project_location = %s, 
                        proposal_deadline = %s, 
                        job_start_date = %s, 
                        job_end_date = %s, 
                        project_desc = %s, 
                        project_details = %s, 
                        submitted_datetime = %s, 
                        status = %s, 
                        org_code = %s, 
                        project_gid = %s, 
                        priority_level = %s 
                    WHERE wr_id = %s"""
            
            data1 = (
                passed_data["firstname"],
                passed_data["middlename"],
                passed_data["lastname"],
                passed_data["email_address"],
                passed_data["customer_type"],
                passed_data["business_unit"],
                passed_data["project_location"],
                passed_data["proposal_deadline"],
                passed_data["job_start_date"],
                passed_data["job_end_date"],
                passed_data["project_desc"],
                passed_data["project_details"],
                now,
                passed_data["status"],
                passed_data["org_code"],
                passed_data["project_gid"],
                passed_data["priority_level"],
                wr_id
            )
            cur.execute(sql1, data1)
            
            
            # SQL for deleting requested services
            delete_services = """DELETE FROM requested_services WHERE wr_id = %s"""
            cur.execute(delete_services, (wr_id,))
            
            
            # SQL for inserting requested services
            insert_services = """INSERT INTO requested_services (wr_id, service_id, detail_id, org_code) VALUES (%s, %s, %s, %s)"""
            
            # Process each parent and its children
            for parent in passed_data["services"]:
                parent_id = parent.get("parent_id")
                children = parent.get("children", [])

                # Insert the parent with no child if `children` is empty
                if not children:
                    cur.execute(
                        insert_services,
                        (wr_id, parent_id, 0, passed_data["org_code"])
                    )

                # Insert each child
                for child in children:
                    child_id = child.get("child_id")
                    cur.execute(
                        insert_services,
                        (wr_id, parent_id, child_id, passed_data["org_code"])
                    )
            
            
            # SQL for updating remarks
            update_remarks = """UPDATE requested_services 
                                SET remarks = %s 
                                WHERE service_id = %s AND detail_id = %s AND wr_id = %s"""

            # Process the remarks list
            for remark in passed_data["remarkslist"]:
                service_id = remark.get("service_id")
                detail_id = remark.get("detail_id")
                remarkdata = remark.get("remarks")

                cur.execute(update_remarks, (remarkdata, service_id, detail_id, wr_id))
            
            
            # --- refresh work_order_team assignments ---
            delete_team = """
                DELETE FROM work_order_team
                WHERE wr_id = %s
                AND org_code = %s
                AND role IN (%s, %s, %s)
            """
            cur.execute(
                delete_team,
                (wr_id, passed_data["org_code"], "planner", "team lead", "manager")
            )
            
            insert_team = """
                INSERT INTO work_order_team
                (wo_number, user, role, assigned_datetime, org_code, wr_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            # planners
            for planner in valid_planners:
                cur.execute(
                    insert_team,
                    (None, planner, "planner", now, passed_data["org_code"], wr_id)
                )

            # pre-approver = team lead
            cur.execute(
                insert_team,
                (None, pre_approver, "team lead", now, passed_data["org_code"], wr_id)
            )

            # final approver = manager
            cur.execute(
                insert_team,
                (None, approver, "manager", now, passed_data["org_code"], wr_id)
            )
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Request changes saved successfully", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    

    # ---- helper: increment trailing number on wo_code so each WO is unique ----
    def increment_code(code: str, inc: int) -> str:
        code = (code or "").strip()
        m = re.search(r"(.*?)(\d+)$", code)
        if not m:
            return f"{code}-{inc+1:02d}"
        prefix, num = m.group(1), m.group(2)
        width = len(num)
        new_num = int(num) + inc
        return f"{prefix}{new_num:0{width}d}"

    # ---- helper: supports tuple rows OR dict rows (DictCursor) ----
    def row_get(r, key, idx=None, default=None):
        if isinstance(r, dict):
            return r.get(key, default)
        if idx is not None and isinstance(r, (list, tuple)) and len(r) > idx:
            return r[idx]
        return default

    #--- save work request status ----#
    '''
    @app.route('/updateworkrequeststatus', methods=['POST'])
    def updateworkrequeststatus():
        passed_data = request.get_json() or {}

        def is_valid_user(user):
            return user and str(user).strip()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()
            wo_number = 0
            generated = []

            # --------- UPDATE WR STATUS ----------
            sql_update_wr = """UPDATE work_requests SET status = %s WHERE wr_id = %s AND org_code = %s"""
            cur.execute(sql_update_wr, (
                passed_data["status_code"],
                passed_data["wr_id"],
                passed_data["org_code"]
            ))

            # --------- LOG WR STATUS CHANGE ----------
            sql_log_wr = """INSERT INTO status_changes
                            (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            cur.execute(sql_log_wr, (
                "Work Request",
                passed_data["wr_id"],
                passed_data.get("status_code_old", ""),
                passed_data["status_code"],
                passed_data.get("user_login", ""),
                "Change status",
                now,
                "Web App",
                passed_data["org_code"]
            ))

            # --------- TEAM ASSIGNED ----------
            if passed_data["status_code"] == "Team Assigned":
                subjectTitle = f"Work Request {passed_data['wr_code']} - Assigned Team"
                referenceTitle = f"Work Request {passed_data['wr_code']}"
                actionTitle = "assigned a team"

                wac_approved_send_email_notification(
                    passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                )

                # Clean previous team entries
                cur.execute(
                    "DELETE FROM work_order_team WHERE wr_id = %s AND org_code = %s",
                    (passed_data["wr_id"], passed_data["org_code"])
                )

                insert_team_sql = """INSERT INTO work_order_team
                                    (wr_id, user, role, assigned_datetime, org_code)
                                    VALUES (%s, %s, %s, %s, %s)"""

                if is_valid_user(passed_data.get("planner")):
                    cur.execute(insert_team_sql, (
                        passed_data["wr_id"], passed_data["planner"], "planner", now, passed_data["org_code"]
                    ))

                if is_valid_user(passed_data.get("pre_approver_1")):
                    cur.execute(insert_team_sql, (
                        passed_data["wr_id"], passed_data["pre_approver_1"], "team lead", now, passed_data["org_code"]
                    ))

                if is_valid_user(passed_data.get("approver")):
                    cur.execute(insert_team_sql, (
                        passed_data["wr_id"], passed_data["approver"], "manager", now, passed_data["org_code"]
                    ))

                # Extra log (kept as in your original)
                cur.execute(sql_log_wr, (
                    "Work Request",
                    passed_data["wr_id"],
                    "Team Assigned",
                    passed_data.get("wo_status", ""),
                    passed_data.get("requested_by", ""),
                    "Assign a team",
                    now,
                    "Web App",
                    passed_data["org_code"]
                ))

            # --------- ACCEPTED: CREATE WO PER REQUESTED_SERVICE DETAIL ----------
            if passed_data["status_code"] == "Accepted":

                fetch_details_sql = """
                    SELECT
                        rs.service_id AS service_id,
                        rs.detail_id  AS detail_id,
                        COALESCE(s.description, '')  AS service_desc,
                        COALESCE(sd.description, '') AS detail_desc
                    FROM requested_services rs
                    LEFT JOIN services s
                        ON s.service_id = rs.service_id
                    AND s.org_code   = rs.org_code
                    LEFT JOIN service_details sd
                        ON sd.detail_id = rs.detail_id
                    AND sd.org_code  = rs.org_code
                    WHERE rs.wr_id = %s
                    AND rs.org_code = %s
                    ORDER BY rs.id ASC
                """
                cur.execute(fetch_details_sql, (passed_data["wr_id"], passed_data["org_code"]))
                requested_rows = cur.fetchall() or []

                # Generate base wo_code once, then increment per row
                base_wo_code = generate_next_wo_number(passed_data["wr_code"])

                # Fallback: if no requested_services, keep old single-WO behavior
                if len(requested_rows) == 0:
                    workdesc_summary = (passed_data.get("work_description") or "").strip()
                    next_wo_code = base_wo_code

                    if passed_data.get("wo_status") == "Started":
                        insert_wo = """INSERT INTO work_orders
                            (wo_type, wo_description, status, due_date, job_start_date,
                            project_name, project_description, location, business_unit,
                            requested_by, created_datetime, wr_id, wo_code, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, %s, %s, %s)"""
                        cur.execute(insert_wo, (
                            "FWO",
                            workdesc_summary,
                            passed_data["wo_status"],
                            passed_data["due_date"],
                            now,
                            passed_data["project_name"],
                            passed_data["project_description"],
                            passed_data["location"],
                            passed_data["business_unit"],
                            passed_data["requested_by"],
                            now,
                            passed_data["wr_id"],
                            next_wo_code,
                            passed_data["org_code"]
                        ))
                    else:
                        insert_wo = """INSERT INTO work_orders
                            (wo_type, wo_description, status, due_date,
                            project_name, project_description, location, business_unit,
                            requested_by, created_datetime, wr_id, wo_code, org_code, proposal_status)
                            VALUES (%s, %s, %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s)"""
                        cur.execute(insert_wo, (
                            "FWO",
                            workdesc_summary,
                            passed_data["wo_status"],
                            passed_data["due_date"],
                            passed_data["project_name"],
                            passed_data["project_description"],
                            passed_data["location"],
                            passed_data["business_unit"],
                            passed_data["requested_by"],
                            now,
                            passed_data["wr_id"],
                            next_wo_code,
                            passed_data["org_code"],
                            "Draft"
                        ))

                    wo_number = cur.lastrowid

                    # Log WO
                    sql_log_wo = """INSERT INTO status_changes
                        (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cur.execute(sql_log_wo, (
                        "Work Order",
                        wo_number,
                        "WR Accepted",
                        passed_data["wo_status"],
                        passed_data["requested_by"],
                        "New work order",
                        now,
                        "Web App",
                        passed_data["org_code"]
                    ))

                    subjectTitle = f"Work Request {passed_data['wr_code']} - Accepted"
                    referenceTitle = f"Work Request {passed_data['wr_code']}"
                    actionTitle = f"accepted. A new Work Order {next_wo_code} has been generated automatically"
                    wac_approved_send_email_notification(
                        passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                    )

                else:
                    # Create 1 WO per requested_services row
                    for idx, r in enumerate(requested_rows):
                        service_id = row_get(r, "service_id", 0)
                        detail_id = row_get(r, "detail_id", 1)
                        service_desc = (row_get(r, "service_desc", 2, "") or "").strip()
                        detail_desc = (row_get(r, "detail_desc", 3, "") or "").strip()

                        #if service_desc and detail_desc:
                        #    wo_desc = f"{service_desc} - {detail_desc}"
                        if detail_desc:
                            wo_desc = detail_desc
                        #elif service_desc:
                        #    wo_desc = service_desc
                        else:
                            wo_desc = (passed_data.get("work_description") or "").strip()

                        next_wo_code = increment_code(base_wo_code, idx)

                        if passed_data.get("wo_status") == "Started":
                            insert_wo = """INSERT INTO work_orders
                                (wo_type, wo_description, status, due_date, job_start_date,
                                project_name, project_description, location, business_unit,
                                requested_by, created_datetime, wr_id, wo_code, org_code)
                                VALUES (%s, %s, %s, %s, %s, %s,
                                        %s, %s, %s, %s,
                                        %s, %s, %s, %s)"""
                            cur.execute(insert_wo, (
                                "FWO",
                                wo_desc,
                                passed_data["wo_status"],
                                passed_data["due_date"],
                                now,
                                passed_data["project_name"],
                                passed_data["project_description"],
                                passed_data["location"],
                                passed_data["business_unit"],
                                passed_data["requested_by"],
                                now,
                                passed_data["wr_id"],
                                next_wo_code,
                                passed_data["org_code"]
                            ))
                        else:
                            insert_wo = """INSERT INTO work_orders
                                (wo_type, wo_description, status, due_date,
                                project_name, project_description, location, business_unit,
                                requested_by, created_datetime, wr_id, wo_code, org_code, proposal_status)
                                VALUES (%s, %s, %s, %s, %s,
                                        %s, %s, %s, %s,
                                        %s, %s, %s, %s, %s)"""
                            cur.execute(insert_wo, (
                                "FWO",
                                wo_desc,
                                passed_data["wo_status"],
                                passed_data["due_date"],
                                passed_data["project_name"],
                                passed_data["project_description"],
                                passed_data["location"],
                                passed_data["business_unit"],
                                passed_data["requested_by"],
                                now,
                                passed_data["wr_id"],
                                next_wo_code,
                                passed_data["org_code"],
                                "Draft"
                            ))

                        new_wo_number = cur.lastrowid
                        if wo_number == 0:
                            wo_number = new_wo_number

                        # Log WO
                        sql_log_wo = """INSERT INTO status_changes
                            (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql_log_wo, (
                            "Work Order",
                            new_wo_number,
                            "WR Accepted",
                            passed_data["wo_status"],
                            passed_data["requested_by"],
                            "New work order (auto-generated per requested service detail)",
                            now,
                            "Web App",
                            passed_data["org_code"]
                        ))

                        generated.append({
                            "wo_number": new_wo_number,
                            "wo_code": next_wo_code,
                            "service_id": service_id,
                            "detail_id": detail_id,
                            "wo_description": wo_desc
                        })

                    # Single email notification, include count
                    subjectTitle = f"Work Request {passed_data['wr_code']} - Accepted"
                    referenceTitle = f"Work Request {passed_data['wr_code']}"
                    actionTitle = f"accepted. {len(generated)} Work Order(s) were generated automatically"
                    wac_approved_send_email_notification(
                        passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                    )

            # --------- DECLINED ----------
            if passed_data["status_code"] == "Declined":
                subjectTitle = f"Work Request {passed_data['wr_code']} - Declined"
                referenceTitle = f"Work Request {passed_data['wr_code']}"
                actionTitle = "declined."
                wac_approved_send_email_notification(
                    passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                )

            # --------- ON HOLD ----------
            if passed_data["status_code"] == "On Hold":
                subjectTitle = f"Work Request {passed_data['wr_code']} - On Hold"
                referenceTitle = f"Work Request {passed_data['wr_code']}"
                actionTitle = "put on hold."
                wac_approved_send_email_notification(
                    passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                )

            conn.commit()
            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            resp = {
                "message": "Status updated",
                "result": wo_number,
                "generated_work_orders": generated
            }
            return jsonify(resp), 201

        except Exception as e:
            # full traceback for real debugging
            try:
                logger.exception("ERROR /updateworkrequeststatus")
            except Exception:
                # if logger not configured
                print(traceback.format_exc())

            return jsonify({
                "error": "Internal server error",
                "detail": str(e)
            }), 500
    '''
    #--- save work request status ----#
    @app.route('/updateworkrequeststatus', methods=['POST'])
    def updateworkrequeststatus():
        passed_data = request.get_json() or {}

        def is_valid_user(user):
            return user and str(user).strip()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()
            wo_number = 0
            generated = []

            # helper: copy WR team to newly created WO
            def copy_wr_team_to_wo(cur, wr_id, wo_number, org_code):
                fetch_team_sql = """
                    SELECT user, role, assigned_datetime, org_code, wr_id
                    FROM work_order_team
                    WHERE wr_id = %s
                    AND org_code = %s
                """
                cur.execute(fetch_team_sql, (wr_id, org_code))
                team_rows = cur.fetchall() or []

                insert_team_to_wo_sql = """
                    INSERT INTO work_order_team
                        (wo_number, user, role, assigned_datetime, org_code)
                    VALUES (%s, %s, %s, %s, %s)
                """

                for team_row in team_rows:
                    team_user = row_get(team_row, "user", 0)
                    team_role = row_get(team_row, "role", 1)
                    team_assigned_datetime = row_get(team_row, "assigned_datetime", 2)
                    team_org_code = row_get(team_row, "org_code", 3)

                    cur.execute(insert_team_to_wo_sql, (
                        wo_number,
                        team_user,
                        team_role,
                        team_assigned_datetime,
                        team_org_code
                    ))

            # --------- UPDATE WR STATUS ----------
            sql_update_wr = """UPDATE work_requests SET status = %s WHERE wr_id = %s AND org_code = %s"""
            cur.execute(sql_update_wr, (
                passed_data["status_code"],
                passed_data["wr_id"],
                passed_data["org_code"]
            ))

            # --------- LOG WR STATUS CHANGE ----------
            sql_log_wr = """INSERT INTO status_changes
                            (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            cur.execute(sql_log_wr, (
                "Work Request",
                passed_data["wr_id"],
                passed_data.get("status_code_old", ""),
                passed_data["status_code"],
                passed_data.get("user_login", ""),
                "Change status",
                now,
                "Web App",
                passed_data["org_code"]
            ))

            # --------- TEAM ASSIGNED ----------
            if passed_data["status_code"] == "Team Assigned":
                subjectTitle = f"Work Request {passed_data['wr_code']} - Assigned Team"
                referenceTitle = f"Work Request {passed_data['wr_code']}"
                actionTitle = "assigned a team"

                wac_approved_send_email_notification(
                    passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                )

                # Clean previous team entries
                cur.execute(
                    "DELETE FROM work_order_team WHERE wr_id = %s AND org_code = %s",
                    (passed_data["wr_id"], passed_data["org_code"])
                )

                insert_team_sql = """INSERT INTO work_order_team
                                    (wr_id, user, role, assigned_datetime, org_code)
                                    VALUES (%s, %s, %s, %s, %s)"""

                if is_valid_user(passed_data.get("planner")):
                    cur.execute(insert_team_sql, (
                        passed_data["wr_id"], passed_data["planner"], "planner", now, passed_data["org_code"]
                    ))

                if is_valid_user(passed_data.get("pre_approver_1")):
                    cur.execute(insert_team_sql, (
                        passed_data["wr_id"], passed_data["pre_approver_1"], "team lead", now, passed_data["org_code"]
                    ))

                if is_valid_user(passed_data.get("approver")):
                    cur.execute(insert_team_sql, (
                        passed_data["wr_id"], passed_data["approver"], "manager", now, passed_data["org_code"]
                    ))

                # Extra log (kept as in your original)
                cur.execute(sql_log_wr, (
                    "Work Request",
                    passed_data["wr_id"],
                    "Team Assigned",
                    passed_data.get("wo_status", ""),
                    passed_data.get("requested_by", ""),
                    "Assign a team",
                    now,
                    "Web App",
                    passed_data["org_code"]
                ))

            # --------- ACCEPTED: CREATE WO PER REQUESTED_SERVICE DETAIL ----------
            if passed_data["status_code"] == "Accepted":

                fetch_details_sql = """
                    SELECT
                        rs.service_id AS service_id,
                        rs.detail_id  AS detail_id,
                        COALESCE(s.description, '')  AS service_desc,
                        COALESCE(sd.description, '') AS detail_desc
                    FROM requested_services rs
                    LEFT JOIN services s
                        ON s.service_id = rs.service_id
                    AND s.org_code   = rs.org_code
                    LEFT JOIN service_details sd
                        ON sd.detail_id = rs.detail_id
                    AND sd.org_code  = rs.org_code
                    WHERE rs.wr_id = %s
                    AND rs.org_code = %s
                    ORDER BY rs.id ASC
                """
                cur.execute(fetch_details_sql, (passed_data["wr_id"], passed_data["org_code"]))
                requested_rows = cur.fetchall() or []

                # Generate base wo_code once, then increment per row
                base_wo_code = generate_next_wo_number(passed_data["wr_code"])

                # Fallback: if no requested_services, keep old single-WO behavior
                if len(requested_rows) == 0:
                    workdesc_summary = (passed_data.get("work_description") or "").strip()
                    next_wo_code = base_wo_code

                    if passed_data.get("wo_status") == "Started":
                        insert_wo = """INSERT INTO work_orders
                            (wo_type, wo_description, status, due_date, job_start_date,
                            project_name, project_description, location, business_unit,
                            requested_by, created_datetime, wr_id, wo_code, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, %s, %s, %s)"""
                        cur.execute(insert_wo, (
                            "FWO",
                            workdesc_summary,
                            passed_data["wo_status"],
                            passed_data["due_date"],
                            now,
                            passed_data["project_name"],
                            passed_data["project_description"],
                            passed_data["location"],
                            passed_data["business_unit"],
                            passed_data["requested_by"],
                            now,
                            passed_data["wr_id"],
                            next_wo_code,
                            passed_data["org_code"]
                        ))
                    else:
                        insert_wo = """INSERT INTO work_orders
                            (wo_type, wo_description, status, due_date,
                            project_name, project_description, location, business_unit,
                            requested_by, created_datetime, wr_id, wo_code, org_code, proposal_status)
                            VALUES (%s, %s, %s, %s, %s,
                                    %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s)"""
                        cur.execute(insert_wo, (
                            "FWO",
                            workdesc_summary,
                            passed_data["wo_status"],
                            passed_data["due_date"],
                            passed_data["project_name"],
                            passed_data["project_description"],
                            passed_data["location"],
                            passed_data["business_unit"],
                            passed_data["requested_by"],
                            now,
                            passed_data["wr_id"],
                            next_wo_code,
                            passed_data["org_code"],
                            "Draft"
                        ))

                    wo_number = cur.lastrowid

                    # NEW: copy WR team to this newly created WO
                    copy_wr_team_to_wo(
                        cur,
                        passed_data["wr_id"],
                        wo_number,
                        passed_data["org_code"]
                    )

                    # Log WO
                    sql_log_wo = """INSERT INTO status_changes
                        (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cur.execute(sql_log_wo, (
                        "Work Order",
                        wo_number,
                        "WR Accepted",
                        passed_data["wo_status"],
                        passed_data["requested_by"],
                        "New work order",
                        now,
                        "Web App",
                        passed_data["org_code"]
                    ))

                    subjectTitle = f"Work Request {passed_data['wr_code']} - Accepted"
                    referenceTitle = f"Work Request {passed_data['wr_code']}"
                    actionTitle = f"accepted. A new Work Order {next_wo_code} has been generated automatically"
                    wac_approved_send_email_notification(
                        passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                    )

                else:
                    # Create 1 WO per requested_services row
                    for idx, r in enumerate(requested_rows):
                        service_id = row_get(r, "service_id", 0)
                        detail_id = row_get(r, "detail_id", 1)
                        service_desc = (row_get(r, "service_desc", 2, "") or "").strip()
                        detail_desc = (row_get(r, "detail_desc", 3, "") or "").strip()

                        #if service_desc and detail_desc:
                        #    wo_desc = f"{service_desc} - {detail_desc}"
                        if detail_desc:
                            wo_desc = detail_desc
                        #elif service_desc:
                        #    wo_desc = service_desc
                        else:
                            wo_desc = (passed_data.get("work_description") or "").strip()

                        next_wo_code = increment_code(base_wo_code, idx)

                        if passed_data.get("wo_status") == "Started":
                            insert_wo = """INSERT INTO work_orders
                                (wo_type, wo_description, status, due_date, job_start_date,
                                project_name, project_description, location, business_unit,
                                requested_by, created_datetime, wr_id, wo_code, org_code)
                                VALUES (%s, %s, %s, %s, %s, %s,
                                        %s, %s, %s, %s,
                                        %s, %s, %s, %s)"""
                            cur.execute(insert_wo, (
                                "FWO",
                                wo_desc,
                                passed_data["wo_status"],
                                passed_data["due_date"],
                                now,
                                passed_data["project_name"],
                                passed_data["project_description"],
                                passed_data["location"],
                                passed_data["business_unit"],
                                passed_data["requested_by"],
                                now,
                                passed_data["wr_id"],
                                next_wo_code,
                                passed_data["org_code"]
                            ))
                        else:
                            insert_wo = """INSERT INTO work_orders
                                (wo_type, wo_description, status, due_date,
                                project_name, project_description, location, business_unit,
                                requested_by, created_datetime, wr_id, wo_code, org_code, proposal_status)
                                VALUES (%s, %s, %s, %s, %s,
                                        %s, %s, %s, %s,
                                        %s, %s, %s, %s, %s)"""
                            cur.execute(insert_wo, (
                                "FWO",
                                wo_desc,
                                passed_data["wo_status"],
                                passed_data["due_date"],
                                passed_data["project_name"],
                                passed_data["project_description"],
                                passed_data["location"],
                                passed_data["business_unit"],
                                passed_data["requested_by"],
                                now,
                                passed_data["wr_id"],
                                next_wo_code,
                                passed_data["org_code"],
                                "Draft"
                            ))

                        new_wo_number = cur.lastrowid
                        if wo_number == 0:
                            wo_number = new_wo_number

                        # NEW: copy WR team to each newly created WO
                        copy_wr_team_to_wo(
                            cur,
                            passed_data["wr_id"],
                            new_wo_number,
                            passed_data["org_code"]
                        )

                        # Log WO
                        sql_log_wo = """INSERT INTO status_changes
                            (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql_log_wo, (
                            "Work Order",
                            new_wo_number,
                            "WR Accepted",
                            passed_data["wo_status"],
                            passed_data["requested_by"],
                            "New work order (auto-generated per requested service detail)",
                            now,
                            "Web App",
                            passed_data["org_code"]
                        ))

                        generated.append({
                            "wo_number": new_wo_number,
                            "wo_code": next_wo_code,
                            "service_id": service_id,
                            "detail_id": detail_id,
                            "wo_description": wo_desc
                        })

                    # Single email notification, include count
                    subjectTitle = f"Work Request {passed_data['wr_code']} - Accepted"
                    referenceTitle = f"Work Request {passed_data['wr_code']}"
                    actionTitle = f"accepted. {len(generated)} Work Order(s) were generated automatically"
                    wac_approved_send_email_notification(
                        passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                    )

            # --------- DECLINED ----------
            if passed_data["status_code"] == "Declined":
                subjectTitle = f"Work Request {passed_data['wr_code']} - Declined"
                referenceTitle = f"Work Request {passed_data['wr_code']}"
                actionTitle = "declined."
                wac_approved_send_email_notification(
                    passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                )

            # --------- ON HOLD ----------
            if passed_data["status_code"] == "On Hold":
                subjectTitle = f"Work Request {passed_data['wr_code']} - On Hold"
                referenceTitle = f"Work Request {passed_data['wr_code']}"
                actionTitle = "put on hold."
                wac_approved_send_email_notification(
                    passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle
                )

            conn.commit()
            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            resp = {
                "message": "Status updated",
                "result": wo_number,
                "generated_work_orders": generated
            }
            return jsonify(resp), 201

        except Exception as e:
            # full traceback for real debugging
            try:
                logger.exception("ERROR /updateworkrequeststatus")
            except Exception:
                # if logger not configured
                print(traceback.format_exc())

            return jsonify({
                "error": "Internal server error",
                "detail": str(e)
            }), 500


    #--- create another work order for a certain work request ----#
    @app.route('/createanotherworkorder', methods=['POST'])
    def createanotherworkorder():
        passed_data = request.get_json()

        def is_valid_user(user):
            return user and str(user).strip()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            wo_number = 0
            
            #--- if work request status is Accepted ---
            if passed_data["status_code"] == "Accepted":          
                
                #workdesc_summary = summarize_text_with_bedrock(passed_data["work_description"], alt_prompt="Rewrite the following content as a single clear, professional, and concise statement suitable for saving in a database text field. Do not include titles or bullet points.")
                workdesc_summary = passed_data["work_description"]

                next_wo_code = generate_next_wo_number(passed_data["wr_code"])

                if passed_data["wo_status"] == "Started":
                    insert_wo = """INSERT INTO work_orders (wo_type, wo_description, planner, status, due_date, job_start_date, project_name, project_description, location, business_unit, requested_by, created_datetime, wr_id, wo_code, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    
                    # Insert a new record
                    cur.execute(insert_wo, ("FWO", workdesc_summary, passed_data["planner"], passed_data["wo_status"], passed_data["due_date"], now, passed_data["project_name"], passed_data["project_description"], passed_data["location"], passed_data["business_unit"], passed_data["requested_by"], now, passed_data["wr_id"], next_wo_code, passed_data["org_code"]
                    ))
                else:
                    insert_wo = """INSERT INTO work_orders (wo_type, wo_description, planner, status, due_date, project_name, project_description, location, business_unit, requested_by, created_datetime, wr_id, wo_code, org_code, proposal_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

                    # Insert a new record
                    cur.execute(insert_wo, ("FWO", workdesc_summary, passed_data["planner"], passed_data["wo_status"], passed_data["due_date"], passed_data["project_name"], passed_data["project_description"], passed_data["location"], passed_data["business_unit"], passed_data["requested_by"], now, passed_data["wr_id"], next_wo_code, passed_data["org_code"], "Draft"
                    ))
                
                # Get the newly created work order number
                wo_number = cur.lastrowid

                subjectTitle = f"Work Request {passed_data['wr_code']} - Accepted"
                referenceTitle = f"Work Request {passed_data['wr_code']}"
                actionTitle = f"accepted. A new Work Order {next_wo_code} has been generated automatically"

                wac_approved_send_email_notification(passed_data["requested_by"], referenceTitle, subjectTitle, actionTitle)

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New WO created", "result": wo_number}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save reference work order promotion to final work order ----#
    @app.route('/updatewopromote', methods=['POST'])
    def updatewopromote():
        passed_data = request.get_json()

        def is_valid_user(user):
            return user and str(user).strip()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            sql1 = """UPDATE work_orders SET wo_type = %s, planner = %s WHERE wo_number = %s AND org_code = %s"""
            data1 = ("FWO", passed_data["planner"], passed_data["wo_number"], passed_data["org_code"])
            
            cur.execute(sql1, data1)

            # SQL for inserting into status change logs
            sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = ("Work Order", passed_data["wo_number"], "Reference", "New", passed_data["user_login"], "Promote to work order", now, "Web App", passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # Clean previous approver entries for this work order
            cur.execute("DELETE FROM work_order_team WHERE wo_number = %s AND org_code = %s", (passed_data["wo_number"], passed_data["org_code"]))

            # Insert fresh team entries if present
            insert_team_sql = """INSERT INTO work_order_team (wo_number, user, role,        assigned_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""

            if is_valid_user(passed_data.get("planner")):
                cur.execute(insert_team_sql, (passed_data["wo_number"], passed_data["planner"], 'planner', now, passed_data["org_code"]))

            if is_valid_user(passed_data.get("pre_approver_1")):
                cur.execute(insert_team_sql, (passed_data["wo_number"], passed_data["pre_approver_1"], 'team lead', now, passed_data["org_code"]))

            if is_valid_user(passed_data.get("pre_approver_2")):
                cur.execute(insert_team_sql, (passed_data["wo_number"], passed_data["pre_approver_2"], 'team lead', now, passed_data["org_code"]))

            if is_valid_user(passed_data.get("approver")):
                cur.execute(insert_team_sql, (passed_data["wo_number"], passed_data["approver"], 'manager', now, passed_data["org_code"]))

            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Status updated", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save reference work order promotion to final work order ----#
    @app.route('/updateworoutingchange', methods=['PUT'])
    def updateworoutingchange():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # Insert fresh team entries if present
            update_team_sql = """UPDATE work_order_team SET user = %s, assigned_datetime = %s WHERE id = %s AND org_code = %s"""

            cur.execute(update_team_sql, (passed_data["user"], now, passed_data["id"], passed_data["org_code"]))

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Status updated", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save work order status ----#
    '''
    @app.route('/updateworkorderstatus', methods=['POST'])
    def updateworkorderstatus():
        passed_data = request.get_json()

        def is_valid_user(user):
            return user and str(user).strip()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            wo_number = 0
            
            if passed_data["status_code"] == "Started":
                sql1 = """UPDATE work_orders SET status = %s, job_start_date = %s WHERE wo_number = %s AND org_code = %s"""
                data1 = (passed_data["status_code"], now, passed_data["wo_number"], passed_data["org_code"])
            elif passed_data["status_code"] == "Completed":
                sql1 = """UPDATE work_orders SET status = %s, job_end_date = %s WHERE wo_number = %s AND org_code = %s"""
                data1 = (passed_data["status_code"], passed_data["date_completed"], passed_data["wo_number"], passed_data["org_code"])
            else:    
                sql1 = """UPDATE work_orders SET status = %s, proposal_status = %s WHERE wo_number = %s AND org_code = %s"""
                data1 = (passed_data["status_code"], "Awarded", passed_data["wo_number"], passed_data["org_code"])
            
            cur.execute(sql1, data1)

            # SQL for inserting into status change logs
            sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = ("Work Order", passed_data["wo_number"], passed_data["status_code_old"], passed_data["status_code"], passed_data["user_login"], "Change status", now, "Web App", passed_data["org_code"])
            
            cur.execute(sql1, data1)

            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Status updated", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    '''
    #--- save work order status (with auto sync to ECM once work order is completed ----#
    @app.route('/updateworkorderstatus', methods=['POST'])
    def updateworkorderstatus():
        passed_data = request.get_json()

        def is_valid_user(user):
            return user and str(user).strip()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            wo_number = 0
            
            if passed_data["status_code"] == "Started":
                sql1 = """UPDATE work_orders SET status = %s, job_start_date = %s WHERE wo_number = %s AND org_code = %s"""
                data1 = (passed_data["status_code"], now, passed_data["wo_number"], passed_data["org_code"])

            elif passed_data["status_code"] == "Completed":
                sql1 = """UPDATE work_orders SET status = %s, job_end_date = %s, ecm_sync = %s, ecm_sync_datetime = NULL WHERE wo_number = %s AND org_code = %s"""
                data1 = (passed_data["status_code"], passed_data["date_completed"], "Pending", passed_data["wo_number"], passed_data["org_code"])

            else:    
                sql1 = """UPDATE work_orders SET status = %s, proposal_status = %s WHERE wo_number = %s AND org_code = %s"""
                data1 = (passed_data["status_code"], "Awarded", passed_data["wo_number"], passed_data["org_code"])
            
            cur.execute(sql1, data1)

            # SQL for inserting into status change logs
            sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = ("Work Order", passed_data["wo_number"], passed_data["status_code_old"], passed_data["status_code"], passed_data["user_login"], "Change status", now, "Web App", passed_data["org_code"])
            
            cur.execute(sql1, data1)

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()

            # Send to SQS only after successful DB commit.
            # This should not block or rollback the status update if SQS fails.
            if passed_data["status_code"] == "Completed":
                try:
                    print(
                        f"EDMS SQS TRIGGERED "
                        f"WO={passed_data['wo_number']} "
                        f"ORG={passed_data['org_code']}"
                    )

                    send_edms_ingestion_message(
                        org_code=passed_data["org_code"],
                        wo_number=passed_data["wo_number"],
                        wo_code=passed_data.get("wo_code")
                    )

                    print(
                        f"EDMS SQS SENT "
                        f"WO={passed_data['wo_number']}"
                    )
                except Exception as sqs_error:
                    print("EDMS SQS send failed:", str(sqs_error))
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Status updated", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save proposal status ----#
    @app.route('/updateproposalstatus', methods=['POST'])
    def updateproposalstatus():
        passed_data = request.get_json()

        #logger.info(passed_data)

        def is_valid_user(user):
            return user and str(user).strip()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            #wo_number = 0
            
            sql1 = """UPDATE work_orders SET proposal_status = %s WHERE wo_number = %s AND org_code = %s"""
            data1 = (passed_data["status_code"], passed_data["wo_number"], passed_data["org_code"])
            
            cur.execute(sql1, data1)

            # SQL for inserting into status change logs
            sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = ("Work Order", passed_data["wo_number"], passed_data["status_code_old"], passed_data["status_code"], passed_data["user_login"], "Change proposal status", now, "Web App", passed_data["org_code"])
            
            cur.execute(sql1, data1)

            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Status updated", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    #--- save work order status comment ----#
    @app.route('/saveworkordercomment', methods=['POST'])
    def saveworkordercomment():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting into work order comments
            sql1 = """INSERT INTO wo_comments (wo_number, comments, commented_by, commented_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
            data1 = (passed_data["wo_number"], passed_data["comment"], passed_data["commented_by"], now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Comment inserted", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    #--- save new work request attachments ----#
    @app.route('/postwrattachments', methods=['POST'])
    def postwrattachments():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting attachments
            insert_attachment = """INSERT INTO wr_attachments (wr_id, file, org_code) VALUES (%s, %s, %s)"""

            # Process attachments array
            for filenme in passed_data["attachments"]:
                cur.execute(insert_attachment, (passed_data["wr_id"], filenme, passed_data["org_code"]))

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Request File Attachments created successfully", "result": "Ok"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new work order attachments ----#
    '''
    @app.route('/postwoattachments', methods=['POST'])
    def postwoattachments():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting attachments
            insert_attachment = """INSERT INTO wo_attachments (wo_number, file, org_code) VALUES (%s, %s, %s)"""

            # Process attachments array
            for filenme in passed_data["attachments"]:
                cur.execute(insert_attachment, (passed_data["wo_number"], filenme, passed_data["org_code"]))

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New WO File Attachments created successfully", "result": "Ok"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    '''
    #--- save new work order attachments ----#
    @app.route('/postwoattachments', methods=['POST'])
    def postwoattachments():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()

            # ✅ add file_title column (attachment type)
            insert_attachment = """
                INSERT INTO wo_attachments (wo_number, file, file_title, org_code)
                VALUES (%s, %s, %s, %s)
            """

            attachments = passed_data.get("attachments", [])

            for att in attachments:
                # ✅ supports both: string OR dict
                if isinstance(att, dict):
                    filename = (att.get("file") or "").strip()
                    file_title = (att.get("file_title") or "").strip()
                else:
                    filename = str(att).strip()
                    file_title = ""  # old clients won't send type

                if filename:
                    cur.execute(
                        insert_attachment,
                        (passed_data["wo_number"], filename, file_title, passed_data["org_code"])
                    )

            conn.commit()

            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            return jsonify({"message": "New WO File Attachments created successfully", "result": "Ok"}), 201

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    

    #--- save response output of work management platform ----#
    @app.route('/postworkmgtresponse', methods=['POST'])
    def postworkmgtresponse():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting work request data
            sql1 = """INSERT INTO wr_pm_data (wr_id, resource_type, gid, details, org_code, posted_datetime) VALUES (%s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["wr_id"], passed_data["resource_type"], passed_data["gid"], passed_data["details"], passed_data["org_code"], now)
            
            cur.execute(sql1, data1)
            
            # Get the newly created primary key id
            pk_id = cur.lastrowid
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Request created successfully", "result": pk_id}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500

    # update app inbox for messages have been read
    @app.route('/updatemessageread', methods=['PUT'])
    def updatemessageread():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            # SQL for updating read datetime in app_inbox
            #sql1 = """UPDATE app_chatbox SET read_datetime = %s WHERE task_gid = %s AND #read_datetime IS NULL"""
            #data1 = (now, passed_data["task_gid"])  
            sql1 = """UPDATE app_chatbox SET read_datetime = %s WHERE project_gid = %s AND read_datetime IS NULL"""
            data1 = (now, passed_data["project_gid"])  
            
            cur.execute(sql1, data1)
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update app inbox for messages have been read by the user
    @app.route('/updatemessagereaduser', methods=['PUT'])
    def updatemessagereaduser():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            # SQL for updating read datetime in app_inbox
            sql1 = """UPDATE app_inbox SET status = %s, read_datetime = %s WHERE recipient = %s AND status = %s"""
            data1 = ('read', now, passed_data["user_login"], 'unread')  
            
            cur.execute(sql1, data1)
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update approval request
    '''
    @app.route('/updateapproval', methods=['PUT'])
    def updateapproval():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE approval_requests SET acted_by = %s, acted_datetime = %s, comment = %s, action_status = %s WHERE id = %s AND org_code = %s"""
            data1 = (passed_data["acted_by"], now, passed_data["comment"], passed_data["action_status"], passed_data["id"], passed_data["org_code"]) 

            cur.execute(sql1, data1)
        
            sql1 = """INSERT INTO wo_comments (wo_number, comments, commented_by, commented_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
            data1 = (passed_data["txn_reference"], passed_data["comment"], passed_data["acted_by"], now, passed_data["org_code"]) 

            cur.execute(sql1, data1)
            
            if passed_data["txn_type"] == "Work Order":
                if passed_data["action_status"] == "Rejected":
                    sql1 = """UPDATE work_orders SET status = %s, cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
                    data1 = ("Cancelled", passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])
                else:
                    #--- update cost type used & status to 'Started' if PI or ES is final approved ---
                    ##if passed_data["action_status"] == "Overall Lead Approved" and (passed_data#["service_id"] == 2 or passed_data["service_id"] == 4):
                    if (
                        passed_data["action_status"] == "Overall Lead Approved"
                        and passed_data["service_id"] in (2, 4)
                        ):

                        sql1 = """UPDATE work_orders SET status = 'Started', proposal_status = 'Pending Client Review', job_start_date = %s, cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
                        data1 = (now, passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])
                    #--- PD =1, O&M = 3
                    elif (passed_data["action_status"] == "Team Lead Approved"
                        and passed_data["service_id"] in (1, 3)):
                        sql1 = """UPDATE work_orders SET status = 'Completed', cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
                        data1 = (passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])
                    else:
                        sql1 = """UPDATE work_orders SET cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
                        data1 = (passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])
                
                cur.execute(sql1, data1)

                # SQL for inserting into status change logs
                sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data1 = ("Work Order", passed_data["txn_reference"], passed_data["approval_type"], passed_data["action_status"], passed_data["acted_by"], "Change status", now, "Web App", passed_data["org_code"])
            
                cur.execute(sql1, data1)

                #--- get owner email address for notification
                if passed_data["action_status"] == "Overall Lead Approved":
                    sql2 = """SELECT requested_by FROM work_orders WHERE wo_number = %s AND org_code = %s"""
                    data2 = (passed_data["txn_reference"], passed_data["org_code"])
                    
                    cur.execute(sql2, data2)
                    createdBy = cur.fetchall()
                    createdByEmail = createdBy[0]['requested_by']
                    subjectTitle = f"{passed_data['txn_type']} {passed_data['wo_code']} - Approved"
                    referenceTitle = f"{passed_data['txn_type']} {passed_data['wo_code']}"
                    actionTitle = "approved"
                    
                    wac_approved_send_email_notification(createdByEmail, referenceTitle, subjectTitle, actionTitle)

            if passed_data["txn_type"] == "Work Request":
                sql1 = """UPDATE work_requests SET status = %s WHERE wr_id = %s AND org_code = %s"""
                data1 = (passed_data["action_status"], passed_data["txn_reference"], passed_data["org_code"])
                
                cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()

            pusher_client.trigger('inbox-channel', 'new-message', {'refresh': True})
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    '''
    # update approval request (with auto sync to ECM once work order is completed)
    @app.route('/updateapproval', methods=['PUT'])
    def updateapproval():
        passed_data = request.get_json()
        send_to_edms_sqs = False
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            sql1 = """UPDATE approval_requests SET acted_by = %s, acted_datetime = %s, comment = %s, action_status = %s WHERE id = %s AND org_code = %s"""
            data1 = (passed_data["acted_by"], now, passed_data["comment"], passed_data["action_status"], passed_data["id"], passed_data["org_code"]) 

            cur.execute(sql1, data1)
        
            sql1 = """INSERT INTO wo_comments (wo_number, comments, commented_by, commented_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
            data1 = (passed_data["txn_reference"], passed_data["comment"], passed_data["acted_by"], now, passed_data["org_code"]) 

            cur.execute(sql1, data1)
            
            if passed_data["txn_type"] == "Work Order":
                if passed_data["action_status"] == "Rejected":
                    sql1 = """UPDATE work_orders SET status = %s, cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
                    data1 = ("Cancelled", passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])
                else:
                    if (
                        passed_data["action_status"] == "Overall Lead Approved"
                        and passed_data["service_id"] in (2, 4)
                        ):

                        sql1 = """UPDATE work_orders SET status = 'Started', proposal_status = 'Pending Client Review', job_start_date = %s, cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
                        data1 = (now, passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])

                    elif (passed_data["action_status"] == "Team Lead Approved"
                        and passed_data["service_id"] in (1, 3)):
                        sql1 = """UPDATE work_orders SET status = 'Completed', cost_type_used = %s, ecm_sync = %s, ecm_sync_datetime = NULL WHERE wo_number = %s AND org_code = %s"""
                        data1 = (passed_data["cost_type"], "Pending", passed_data["txn_reference"], passed_data["org_code"])

                        send_to_edms_sqs = True

                    else:
                        sql1 = """UPDATE work_orders SET cost_type_used = %s WHERE wo_number = %s AND org_code = %s"""
                        data1 = (passed_data["cost_type"], passed_data["txn_reference"], passed_data["org_code"])
                
                cur.execute(sql1, data1)

                sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data1 = ("Work Order", passed_data["txn_reference"], passed_data["approval_type"], passed_data["action_status"], passed_data["acted_by"], "Change status", now, "Web App", passed_data["org_code"])
            
                cur.execute(sql1, data1)

                if passed_data["action_status"] == "Overall Lead Approved":
                    sql2 = """SELECT requested_by FROM work_orders WHERE wo_number = %s AND org_code = %s"""
                    data2 = (passed_data["txn_reference"], passed_data["org_code"])
                    
                    cur.execute(sql2, data2)
                    createdBy = cur.fetchall()
                    createdByEmail = createdBy[0]['requested_by']
                    subjectTitle = f"{passed_data['txn_type']} {passed_data['wo_code']} - Approved"
                    referenceTitle = f"{passed_data['txn_type']} {passed_data['wo_code']}"
                    actionTitle = "approved"
                    
                    wac_approved_send_email_notification(createdByEmail, referenceTitle, subjectTitle, actionTitle)

            if passed_data["txn_type"] == "Work Request":
                sql1 = """UPDATE work_requests SET status = %s WHERE wr_id = %s AND org_code = %s"""
                data1 = (passed_data["action_status"], passed_data["txn_reference"], passed_data["org_code"])
                
                cur.execute(sql1, data1)
            
            conn.commit()
            
            cur.close()
            conn.close()

            if send_to_edms_sqs:
                try:
                    send_edms_ingestion_message(
                        org_code=passed_data["org_code"],
                        wo_number=passed_data["txn_reference"],
                        wo_code=passed_data.get("wo_code")
                    )
                except Exception as sqs_error:
                    print("EDMS SQS send failed:", str(sqs_error))

            pusher_client.trigger('inbox-channel', 'new-message', {'refresh': True})
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update approval request
    @app.route('/submitcostestimate', methods=['POST'])
    def submitcostestimate():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()  # Ensure this function returns the current datetime
            notifyusers = None

            # Get team lead assigned
            if passed_data["approval_type"] == "Pending Team Lead Approval":
                sql3 = """
                    SELECT user FROM work_order_team  
                    WHERE role = %s AND org_code = %s AND wr_id = %s"""
                data3 = ("team lead", passed_data["org_code"], passed_data["wr_id"])
                cur.execute(sql3, data3)
                notifyusers = cur.fetchone()

            # Get overall lead assigned
            elif passed_data["approval_type"] == "Pending Overall Lead Approval":
                sql3 = """
                    SELECT user FROM work_order_team  
                    WHERE role = %s AND org_code = %s AND wr_id = %s"""
                data3 = ("manager", passed_data["org_code"], passed_data["wr_id"])
                cur.execute(sql3, data3)
                notifyusers = cur.fetchone()
            
            # Get planner assigned
            else:
                sql3 = """
                    SELECT user FROM work_order_team  
                    WHERE role = %s AND org_code = %s AND wr_id = %s"""
                data3 = ("planner", passed_data["org_code"], passed_data["wr_id"])
                cur.execute(sql3, data3)
                notifyusers = cur.fetchone()

            # Insert approval request
            sql1 = """
                INSERT INTO approval_requests 
                (txn_type, txn_reference, description, approval_type, requested_by, requested_datetime, org_code, acted_by) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (
                passed_data["txn_type"],
                passed_data["txn_reference"],
                passed_data["description"],
                passed_data["approval_type"],
                passed_data["requested_by"],
                now,
                passed_data["org_code"],
                notifyusers["user"],
            )
            cur.execute(sql1, data1)

            # If transaction type is Work Order, update work_orders table
            if passed_data["txn_type"] == "Work Order":
                #--- update proposal status if service type is PI = 2 or ES = 4 ---
                if passed_data["service_id"] == 2 or passed_data["service_id"] == 4:     
                    sql2 = """
                        UPDATE work_orders 
                        SET proposal_status = %s 
                        WHERE wo_number = %s AND org_code = %s"""
                    data2 = (
                        "Under Internal Review",
                        passed_data["txn_reference"],
                        passed_data["org_code"]
                    )
                    cur.execute(sql2, data2)

                #-- PD = 1 or O&M = 3 ---
                if passed_data["service_id"] == 1 or passed_data["service_id"] == 3:
                    if passed_data["completed_date"] != '':
                        sql2 = """
                            UPDATE work_orders 
                            SET job_end_date = %s 
                            WHERE wo_number = %s AND org_code = %s"""
                        data2 = (
                            passed_data["completed_date"],
                            passed_data["txn_reference"],
                            passed_data["org_code"]
                        )
                        cur.execute(sql2, data2)
                
                # SQL for inserting into status change logs
                sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data1 = ("Work Order", passed_data["txn_reference"], passed_data["approval_type_old"], passed_data["approval_type"], passed_data["user_login"], "Change status", now, "Web App", passed_data["org_code"])
            
                cur.execute(sql1, data1)

            # Notify users for first pre-approval
            if passed_data["approval_type"] == "Pending Team Lead Approval":
                '''
                sql3 = """
                    SELECT user FROM work_order_team  
                    WHERE role = %s AND org_code = %s AND wo_number = %s"""
                data3 = ("team lead", passed_data["org_code"], passed_data["txn_reference"])
                cur.execute(sql3, data3)
                notifyusers = cur.fetchall()
                '''

                '''
                for notifyuser in notifyusers:
                    useremaillogin = notifyuser['user']

                    sql4 = """
                        INSERT INTO app_inbox 
                        (title, message, created_datetime, created_by, recipient, source, status, isbroadcast, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    data4 = (
                        "Team Lead Approval",
                        f"{passed_data['txn_type']} {passed_data['txn_reference']} is awaiting your team lead approval.",
                        now,
                        passed_data["requested_by"],
                        useremaillogin,
                        "wac",
                        "unread",
                        0,
                        passed_data["org_code"]
                    )
                    cur.execute(sql4, data4)

                    subject = f"{passed_data['txn_type']} {passed_data['txn_reference']} - Team Lead Approval"
                    referencetitle = f"{passed_data['txn_type']} {passed_data['txn_reference']}"

                    wac_send_email_notification(useremaillogin, referencetitle, subject, "Team Lead Approval")
                '''
                useremaillogin = notifyusers['user']

                sql4 = """
                        INSERT INTO app_inbox 
                        (title, message, created_datetime, created_by, recipient, source, status, isbroadcast, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data4 = (
                        "Team Lead Approval",
                        f"{passed_data['txn_type']} {passed_data['wo_code']} is awaiting your team lead approval.",
                        now,
                        passed_data["requested_by"],
                        useremaillogin,
                        "wac",
                        "unread",
                        0,
                        passed_data["org_code"]
                )
                cur.execute(sql4, data4)

                subject = f"{passed_data['txn_type']} {passed_data['wo_code']} - Team Lead Approval"
                referencetitle = f"{passed_data['txn_type']} {passed_data['wo_code']}"

                wac_send_email_notification(useremaillogin, referencetitle, subject, "Team Lead Approval")
                        
            # Notify users for final approval
            if passed_data["approval_type"] == "Pending Overall Lead Approval":
                '''
                sql3 = """
                    SELECT user FROM work_order_team  
                    WHERE role = %s AND org_code = %s AND wo_number = %s"""
                data3 = ("manager", passed_data["org_code"], passed_data["txn_reference"])
                cur.execute(sql3, data3)
                notifyusers = cur.fetchall()
                '''
                '''
                for notifyuser in notifyusers:
                    useremaillogin = notifyuser['user']

                    sql4 = """
                        INSERT INTO app_inbox 
                        (title, message, created_datetime, created_by, recipient, source, status, isbroadcast, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    data4 = (
                        "Overall Lead Approval",
                        f"{passed_data['txn_type']} {passed_data['txn_reference']} is awaiting your overall lead approval.",
                        now,
                        passed_data["requested_by"],
                        useremaillogin,
                        "wac",
                        "unread",
                        0,
                        passed_data["org_code"]
                    )
                    cur.execute(sql4, data4)

                    subject = f"{passed_data['txn_type']} {passed_data['txn_reference']} - Overall Lead Approval"
                    referencetitle = f"{passed_data['txn_type']} {passed_data['txn_reference']}"
                    
                    wac_send_email_notification(useremaillogin, referencetitle, subject, "Overall Lead Approval")
                '''
                useremaillogin = notifyusers['user']

                sql4 = """
                        INSERT INTO app_inbox 
                        (title, message, created_datetime, created_by, recipient, source, status, isbroadcast, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                data4 = (
                        "Overall Lead Approval",
                        f"{passed_data['txn_type']} {passed_data['wo_code']} is awaiting your overall lead approval.",
                        now,
                        passed_data["requested_by"],
                        useremaillogin,
                        "wac",
                        "unread",
                        0,
                        passed_data["org_code"]
                )
                cur.execute(sql4, data4)

                subject = f"{passed_data['txn_type']} {passed_data['wo_code']} - Overall Lead Approval"
                referencetitle = f"{passed_data['txn_type']} {passed_data['wo_code']}"
                    
                wac_send_email_notification(useremaillogin, referencetitle, subject, "Overall Lead Approval")

            conn.commit()

            # Close the database connection
            cur.close()
            conn.close()

            pusher_client.trigger('inbox-channel', 'new-message', {'refresh': True})

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            return jsonify({"message": "Posted successfully", "result": "inserted"}), 201

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": "Internal server error"}), 500


    # update material cost change (cost mgt)
    @app.route('/updatematerialcost', methods=['PUT'])
    def updatematerialcost():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            changes = passed_data.get('changes')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            for key, value in changes.items():
                itemcode = int(key)
                unitcost = Decimal(value);
                sql1 = """UPDATE physical_items SET unit_cost = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
                data1 = (unitcost, now, itemcode, org_code)  
            
                cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update labor cost change (cost mgt)
    @app.route('/updatelaborcost', methods=['PUT'])
    def updatelaborcost():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            changes = passed_data.get('changes')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            for key, value in changes.items():
                itemcode = int(key)
                unitcost = Decimal(value);
                sql1 = """UPDATE human_items SET unit_cost = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
                data1 = (unitcost, now, itemcode, org_code)  
            
                cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
            

    # update equipment cost change (cost mgt)
    @app.route('/updateequipmentcost', methods=['PUT'])
    def updateequipmentcost():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            changes = passed_data.get('changes')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            for key, value in changes.items():
                itemcode = int(key)
                unitcost = Decimal(value);
                sql1 = """UPDATE physical_equip_items SET unit_cost = %s, updated_datetime = %s WHERE item_code = %s AND org_code = %s"""
                data1 = (unitcost, now, itemcode, org_code)  
            
                cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
            

    # update work order actual total cost
    @app.route('/updateactualtotalcost', methods=['PUT'])
    def updateactualtotalcost():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            wo_number = passed_data.get('wo_number')
            org_code = passed_data.get('org_code')
            revenue = Decimal(passed_data.get('revenue'))
            actual_total_cost = Decimal(passed_data.get('actual_total_cost'))
            gross_profit = Decimal(passed_data.get('gross_profit'))
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE work_orders SET revenue = %s, actual_total_cost = %s, gross_profit = %s WHERE wo_number = %s AND org_code = %s"""
            data1 = (revenue, actual_total_cost, gross_profit, wo_number, org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save message to app inbox ----#
    @app.route('/postappinbox', methods=['POST'])
    def postappinbox():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting work request data
            sql1 = """INSERT INTO app_chatbox (project_gid, task_gid, task_name, message, created_datetime, created_by, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["project_gid"], passed_data["task_gid"], passed_data["task_name"],passed_data["message"], now, passed_data["created_by"], passed_data["source"], passed_data["org_code"])
            
            logger.info(sql1)
            logger.info(data1)

            cur.execute(sql1, data1)
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()

            pusher_client.trigger('inbox-channel', 'new-message', {'refresh': True})
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Message posted successfully", "result": "posted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            logger.error(str(e))
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save work order design ----#
    @app.route('/postwodesign', methods=['POST'])
    def postwodesign():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()
            
            total_materials_cost = 0.00
            total_materials_cost_low = 0.00
            total_materials_cost_avg = 0.00
            total_labor_cost = 0.00
            total_equipment_cost = 0.00
            
            #--- SAVING COMPATIBLE UNITS ---

            # SQL for checking if a record exists
            
            check_cu = """SELECT COUNT(*) AS count FROM wo_compatible_units 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            
            insert_cu = """INSERT INTO wo_compatible_units (wo_number, task_number, cu_code,            cu_type, quantity, created_datetime, org_code) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            
            update_cu = """UPDATE wo_compatible_units 
                        SET cu_type = %s, quantity = %s, created_datetime = %s 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
            
            # Process each selected CU
            for selected_cu in passed_data["selected_cus"]:
                cu_code = selected_cu.get("code")
                cu_type = selected_cu.get("type")
                quantity = selected_cu.get("quantity")
                org_code = selected_cu.get("org_code")

                # Check if the record exists
                cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_cu, (
                        cu_type, quantity, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_cu, (
                        passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                    ))

            # Create a temporary table for CU codes
            create_temp_table = """CREATE TEMPORARY TABLE temp_cu_codes (cu_code VARCHAR(255) NOT NULL)"""

            # Insert CU codes into the temporary table
            insert_into_temp = """INSERT INTO temp_cu_codes (cu_code) VALUES (%s)"""

            # Delete records not in the selected CU codes
            
            delete_cu = """DELETE FROM wo_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_cu_codes) AND org_code = %s"""
            
            # Execute: Create the temporary table
            cur.execute(create_temp_table)

            # Execute: Insert CU codes into the temporary table
            cu_codes = [cu["code"] for cu in passed_data["selected_cus"]]
            cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
            
            # Execute: Perform the DELETE operation
            cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))


            #--- SAVING CU MATERIALS ---

            # SQL for checking if a record exists
            
            check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_items 
                            WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
            
            # SQL for inserting a new record
            
            insert_material = """INSERT INTO wo_task_physical_items (wo_number, task_number, item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                
            # SQL for updating an existing record
            
            update_material = """UPDATE wo_task_physical_items  
                                SET quantity = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, total_cost = %s, total_cost_low = %s, total_cost_avg = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""

            # Process each selected material
            for selected_material in passed_data["selected_materials"]:
                cu_code = selected_material.get("cu_code")
                item_code = selected_material.get("item_code")
                quantity = float(selected_material.get("quantity", "0") or 0)
                unit_cost = float(selected_material.get("unit_cost", "0") or 0)
                unit_cost_low = float(selected_material.get("unit_cost_low", "0") or 0)
                unit_cost_avg = float(selected_material.get("unit_cost_avg", "0") or 0)
                total_cost = float(quantity) * unit_cost
                total_cost_low = float(quantity) * unit_cost_low
                total_cost_avg = float(quantity) * unit_cost_avg
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_materials_cost = total_materials_cost + total_cost
                total_materials_cost_low = total_materials_cost_low + total_cost_low
                total_materials_cost_avg = total_materials_cost_avg + total_cost_avg
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, cu_code, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_matls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_matls_codes (cu_code, item_code) VALUES (%s, %s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM wo_task_physical_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_matls_codes) AND org_code = %s"""
            
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["cu_code"], material["item_code"])
                for material in passed_data["selected_materials"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            #--- SAVING CU ALTERATIONS ---
            
            insert_alteration = """INSERT INTO wo_cu_alterations (wo_number, cu_code, cu_title, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s)"""
            
            for cu_alteration in passed_data["cu_alterations"]:
                cu_code = cu_alteration.get("cu_code")
                cu_title = cu_alteration.get("cu_title")
                alteration = cu_alteration.get("alteration")
                
                # Insert a new record
                if alteration.strip() != "":
                    cur.execute(insert_alteration, (
                        passed_data["wo_number"], cu_code, cu_title, alteration, now, passed_data["org_code"]
                    ))
                
            
            #--- SAVING CUSTOM MATERIALS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_custom_items 
                            WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

            # SQL for inserting a new record
            insert_material = """INSERT INTO wo_task_physical_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            # SQL for updating an existing record
            update_material = """UPDATE wo_task_physical_custom_items  
                                SET quantity = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, total_cost = %s, total_cost_low = %s, total_cost_avg = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

            # Process each selected material
            for selected_material in passed_data["selected_custom_matls"]:
                item_code = selected_material.get("item_code")
                quantity = float(selected_material.get("quantity", "0") or 0)
                unit_cost = float(selected_material.get("unit_cost", "0") or 0)
                unit_cost_low = float(selected_material.get("unit_cost_low", "0") or 0)
                unit_cost_avg = float(selected_material.get("unit_cost_avg", "0") or 0)
                total_cost = float(quantity) * unit_cost
                total_cost_low = float(quantity) * unit_cost_low
                total_cost_avg = float(quantity) * unit_cost_avg
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_materials_cost = total_materials_cost + total_cost
                total_materials_cost_low = total_materials_cost_low + total_cost_low
                total_materials_cost_avg = total_materials_cost_avg + total_cost_avg
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, now, 
                        passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, unit_cost_low, unit_cost_avg, total_cost, total_cost_low, total_cost_avg, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_cmatls_codes (item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_cmatls_codes (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM wo_task_physical_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_cmatls_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["selected_custom_matls"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            #--- SAVING COST ESTIMATE ----
            
            # SQL for checking if a record exists
            check_cost = """SELECT COUNT(*) AS count FROM wo_cost_estimates 
                        WHERE wo_number = %s AND org_code = %s"""

            # SQL for inserting a new record
            '''
            insert_cost = """INSERT INTO wo_cost_estimates (
                            wo_number,
                            materials_cost,
                            materials_cost_low,
                            materials_cost_avg,
                            total_cost,
                            total_cost_low,
                            total_cost_avg,
                            created_datetime,
                            org_code
                            ) VALUES (
                                %s,
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                (
                                COALESCE((%s * (1 + (COALESCE(mark_up_percent, 0) / 100))), 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0),
                                (
                                COALESCE((%s * (1 + (COALESCE(mark_up_percent, 0) / 100))), 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0),
                                (
                                COALESCE((%s * (1 + (COALESCE(mark_up_percent, 0) / 100))), 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0),
                                %s,
                                %s
                            )""" 
            '''
            insert_cost = """INSERT INTO wo_cost_estimates (
                                wo_number,
                                materials_cost,
                                materials_cost_low,
                                materials_cost_avg,
                                created_datetime,
                                org_code
                            ) VALUES (
                                %s,
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                %s,
                                %s
                            )"""
            # SQL for updating an existing record
            '''
            update_cost = """UPDATE wo_cost_estimates
                            SET
                            materials_cost      = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            materials_cost_low  = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            materials_cost_avg  = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),

                            total_cost = (
                                COALESCE(materials_cost, 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0),

                            total_cost_low = (
                                COALESCE(materials_cost_low, 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0),

                            total_cost_avg = (
                                COALESCE(materials_cost_avg, 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0),

                            created_datetime = %s
                            WHERE wo_number = %s AND org_code = %s"""
            '''
            update_cost = """UPDATE wo_cost_estimates
                            SET
                                materials_cost      = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                materials_cost_low  = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                materials_cost_avg  = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                created_datetime = %s
                            WHERE wo_number = %s AND org_code = %s"""
            
            # Check if the record exists
            cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
            result = cur.fetchall()
            

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cost, (
                    total_materials_cost, total_materials_cost_low, total_materials_cost_avg, now, passed_data["wo_number"], passed_data["org_code"]))
            else:
                # Insert a new record
                cur.execute(insert_cost, (
                    passed_data["wo_number"], total_materials_cost, total_materials_cost_low, total_materials_cost_avg, now, passed_data["org_code"]))
            
            #--- SAVING HUMAN COMPATIBLE UNITS ---

            # SQL for checking if a record exists
            check_cu = """SELECT COUNT(*) AS count FROM wo_human_compatible_units 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""

            # SQL for inserting a new record
            insert_cu = """INSERT INTO wo_human_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        
            # SQL for updating an existing record
            update_cu = """UPDATE wo_human_compatible_units 
                        SET cu_type = %s, quantity = %s, created_datetime = %s 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
            
            # Process each selected CU
            for selected_cu in passed_data["selected_human_cus"]:
                cu_code = selected_cu.get("code")
                cu_type = selected_cu.get("type")
                quantity = selected_cu.get("quantity")
                org_code = selected_cu.get("org_code")

                # Check if the record exists
                cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_cu, (
                        cu_type, quantity, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_cu, (
                        passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                    ))
                    
            # Create a temporary table for CU codes
            create_temp_table = """CREATE TEMPORARY TABLE temp_hcu_codes (cu_code VARCHAR(255) NOT NULL)"""

            # Insert CU codes into the temporary table
            insert_into_temp = """INSERT INTO temp_hcu_codes (cu_code) VALUES (%s)"""

            # Delete records not in the selected CU codes
            delete_cu = """DELETE FROM wo_human_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_hcu_codes) AND org_code = %s"""
            
            # Execute: Create the temporary table
            cur.execute(create_temp_table)

            # Execute: Insert CU codes into the temporary table
            cu_codes = [cu["code"] for cu in passed_data["selected_human_cus"]]
            cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
            
            # Execute: Perform the DELETE operation
            cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

            
            #--- SAVING HUMAN CU LABOR ITEMS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM wo_task_human_items 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO wo_task_human_items (wo_number, task_number, item_code, quantity, duration, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            # SQL for updating an existing record
            update_material = """UPDATE wo_task_human_items  
                                SET quantity = %s, duration = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
            
            # Process each selected labor items
            for selected_material in passed_data["selected_labors"]:
                cu_code = selected_material.get("cu_code")
                item_code = selected_material.get("item_code")
                quantity = float(selected_material.get("quantity", "0") or 0)
                usage = float(selected_material.get("usage", "0") or 0)
                unit_cost = float(selected_material.get("unit_cost", "0") or 0)
                #total_cost = float(quantity) * unit_cost
                total_cost = float(selected_material.get("total_cost", "0") or 0)
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_labor_cost = total_labor_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, usage, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, usage, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_labors_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_labors_codes (cu_code, item_code) VALUES (%s, %s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM wo_task_human_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_labors_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["cu_code"], material["item_code"])
                for material in passed_data["selected_labors"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            #--- SAVING CU LABOR ALTERATIONS ---
            
            insert_alteration_labor = """INSERT INTO wo_cu_alterations (wo_number, cu_code, cu_title, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s)"""
            
            for cu_alteration_labor in passed_data["cu_alterations_labor"]:
                cu_code_labor = cu_alteration_labor.get("cu_code")
                cu_title_labor = cu_alteration_labor.get("cu_title")
                alteration_labor = cu_alteration_labor.get("alteration")
                
                # Insert a new record
                if alteration_labor.strip() != "":
                    cur.execute(insert_alteration_labor, (
                            passed_data["wo_number"], cu_code_labor, cu_title_labor, alteration_labor, now, passed_data["org_code"]
                    ))
            
            #--- SAVING CUSTOM LABOR ITEMS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM wo_task_human_custom_items 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO wo_task_human_custom_items (wo_number, task_number, item_code, quantity, duration, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                
            # SQL for updating an existing record
            update_material = """UPDATE wo_task_human_custom_items  
                                SET quantity = %s, duration = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

            # Process each selected labor items
            for selected_material in passed_data["selected_custom_labors"]:
                item_code = selected_material.get("item_code")
                quantity = float(selected_material.get("quantity", "0") or 0)
                usage = float(selected_material.get("labor_usage", "0") or 0)
                unit_cost = float(selected_material.get("unit_cost", "0") or 0)
                #total_cost = float(quantity) * unit_cost
                total_cost = float(selected_material.get("total_cost", "0") or 0)
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_labor_cost = total_labor_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, usage, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, usage, uom, unit_cost, total_cost, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_hcmatls_codes (item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_hcmatls_codes (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM wo_task_human_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_hcmatls_codes) AND org_code = %s"""
            
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["selected_custom_labors"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            
            #--- SAVING LABOR COST ESTIMATE ----
            
            # SQL for checking if a record exists
            check_cost = """SELECT COUNT(*) AS count FROM wo_cost_estimates 
                        WHERE wo_number = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            '''
            insert_cost = """INSERT INTO wo_cost_estimates (
                            wo_number,
                            labor_cost,
                            total_cost,
                            created_datetime,
                            org_code
                            ) VALUES (
                            %s,
                            (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            (
                                COALESCE(materials_cost, 0) +
                                COALESCE((%s * (1 + (COALESCE(mark_up_percent, 0) / 100))), 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0),
                            %s,
                            %s
                            )"""
            '''
            insert_cost = """INSERT INTO wo_cost_estimates (
                                wo_number,
                                labor_cost,
                                created_datetime,
                                org_code
                            ) VALUES (
                                %s,
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                %s,
                                %s
                            )"""
            # SQL for updating an existing record
            '''
            update_cost = """UPDATE wo_cost_estimates
                            SET
                            labor_cost = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            total_cost = (
                                COALESCE(materials_cost, 0) +
                                COALESCE((%s * (1 + (COALESCE(mark_up_percent, 0) / 100))), 0) +
                                COALESCE(equipment_cost, 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0),
                            created_datetime = %s
                            WHERE wo_number = %s AND org_code = %s"""
            '''
            update_cost = """UPDATE wo_cost_estimates
                            SET
                            labor_cost = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            created_datetime = %s
                            WHERE wo_number = %s AND org_code = %s"""
            
            # Check if the record exists
            cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
            result = cur.fetchall()
            
            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                '''
                cur.execute(update_cost, (
                    total_labor_cost, now, passed_data["wo_number"], passed_data["org_code"]))
                '''
                cur.execute(update_cost, (
                    total_labor_cost,
                    now,
                    passed_data["wo_number"],
                    passed_data["org_code"]
                ))
            else:
                # Insert a new record
                '''
                cur.execute(insert_cost, (
                    passed_data["wo_number"], total_labor_cost, now, passed_data["org_code"]))
                '''
                cur.execute(insert_cost, (
                    passed_data["wo_number"],
                    total_labor_cost,
                    now,
                    passed_data["org_code"]
                ))
            
            #--- SAVING EQUIPMENT COMPATIBLE UNITS ---

            # SQL for checking if a record exists
            check_cu = """SELECT COUNT(*) AS count FROM wo_equip_compatible_units 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            insert_cu = """INSERT INTO wo_equip_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        
            # SQL for updating an existing record
            update_cu = """UPDATE wo_equip_compatible_units 
                        SET cu_type = %s, quantity = %s, created_datetime = %s 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
            
            # Process each selected CU
            for selected_cu in passed_data["selected_equip_cus"]:
                cu_code = selected_cu.get("code")
                cu_type = selected_cu.get("type")
                quantity = selected_cu.get("quantity")
                org_code = selected_cu.get("org_code")

                # Check if the record exists
                cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_cu, (
                        cu_type, quantity, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_cu, (
                        passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                    ))
            
            # Create a temporary table for CU codes
            create_temp_table = """CREATE TEMPORARY TABLE temp_ecu_codes (cu_code VARCHAR(255) NOT NULL)"""

            # Insert CU codes into the temporary table
            insert_into_temp = """INSERT INTO temp_ecu_codes (cu_code) VALUES (%s)"""

            # Delete records not in the selected CU codes
            delete_cu = """DELETE FROM wo_equip_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_ecu_codes) AND org_code = %s"""
            
            # Execute: Create the temporary table
            cur.execute(create_temp_table)

            # Execute: Insert CU codes into the temporary table
            cu_codes = [cu["code"] for cu in passed_data["selected_equip_cus"]]
            cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
            
            # Execute: Perform the DELETE operation
            cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

            
            #--- SAVING EQUIPMENT CU MATERIALS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_equip_items 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO wo_task_physical_equip_items (wo_number, task_number, item_code, quantity, equip_usage, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            update_material = """UPDATE wo_task_physical_equip_items   
                                SET quantity = %s, equip_usage = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # Process each selected material
            ##logger.info(passed_data["selected_equipment"])
            for selected_material in passed_data["selected_equipment"]:
                cu_code = selected_material.get("cu_code")
                item_code = selected_material.get("item_code")
                quantity = float(selected_material.get("quantity", "0") or 0)
                usage = float(selected_material.get("usage", "0") or 0)
                unit_cost = float(selected_material.get("unit_cost", "0") or 0)
                total_cost = (float(quantity) * float(usage)) * unit_cost
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_equipment_cost = total_equipment_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, usage, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, usage, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_ematls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_ematls_codes (cu_code, item_code) VALUES (%s, %s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM wo_task_physical_equip_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_ematls_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["cu_code"], material["item_code"])
                for material in passed_data["selected_equipment"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            #--- SAVING CU EQUIPMENT ALTERATIONS ---
            
            insert_alteration_equipment = """INSERT INTO wo_cu_alterations (wo_number, cu_code, cu_title, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s)"""
            
            for cu_alteration_equipment in passed_data["cu_alterations_equipment"]:
                cu_code_equipment = cu_alteration_equipment.get("cu_code")
                cu_title_equipment = cu_alteration_equipment.get("cu_title")
                alteration_equipment = cu_alteration_equipment.get("alteration")
                
                # Insert a new record
                if alteration_equipment.strip() != "":
                    cur.execute(insert_alteration_equipment, (
                            passed_data["wo_number"], cu_code_equipment, cu_title_equipment, alteration_equipment, now, passed_data["org_code"]
                    ))
            
            
            #--- SAVING EQUIPMENT CUSTOM MATERIALS ---

            # SQL for checking if a record exists
            
            check_material = """SELECT COUNT(*) AS count FROM wo_task_physical_equip_custom_items 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO wo_task_physical_equip_custom_items (wo_number, task_number, item_code, quantity, equip_usage, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                
            # SQL for updating an existing record
            update_material = """UPDATE wo_task_physical_equip_custom_items  
                                SET quantity = %s, equip_usage = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                                
            # Process each selected material
            for selected_material in passed_data["selected_custom_equipment"]:
                item_code = selected_material.get("item_code")
                quantity = float(selected_material.get("quantity", "0") or 0)
                equip_usage = float(selected_material.get("equip_usage", "0") or 0)
                unit_cost = float(selected_material.get("unit_cost", "0") or 0)
                #total_cost = float(quantity) * unit_cost
                total_cost = float(selected_material.get("total_cost", "0") or 0)
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_equipment_cost = total_equipment_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, equip_usage, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, equip_usage, uom, unit_cost, total_cost, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_ecmatls_codes (item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_ecmatls_codes (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM wo_task_physical_equip_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_ecmatls_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["selected_custom_equipment"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            

            #--- SAVING EQUIPMENT COST ESTIMATE ----
            
            # SQL for checking if a record exists
            check_cost = """SELECT COUNT(*) AS count FROM wo_cost_estimates 
                        WHERE wo_number = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            '''
            insert_cost = """INSERT INTO wo_cost_estimates (
                            wo_number,
                            equipment_cost,
                            total_cost,
                            created_datetime,
                            org_code
                            ) VALUES (
                            %s,
                            (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            (
                                COALESCE(materials_cost, 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE((%s * (1 + (COALESCE(mark_up_percent, 0) / 100))), 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0),
                            %s,
                            %s
                            )"""
            '''
            insert_cost = """INSERT INTO wo_cost_estimates (
                                wo_number,
                                equipment_cost,
                                created_datetime,
                                org_code
                            ) VALUES (
                                %s,
                                (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                                %s,
                                %s
                            )"""
            # SQL for updating an existing record
            '''
            update_cost = """UPDATE wo_cost_estimates
                            SET
                            equipment_cost = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            total_cost = (
                                COALESCE(materials_cost, 0) +
                                COALESCE(labor_cost, 0) +
                                COALESCE((%s * (1 + (COALESCE(mark_up_percent, 0) / 100))), 0) +
                                COALESCE(overhead_cost, 0) +
                                COALESCE(contingency_fund, 0)
                            ) - COALESCE(discounts, 0),
                            created_datetime = %s
                            WHERE wo_number = %s AND org_code = %s"""
            '''
            update_cost = """UPDATE wo_cost_estimates
                            SET
                            equipment_cost = (%s * (1 + (COALESCE(mark_up_percent, 0) / 100))),
                            created_datetime = %s
                            WHERE wo_number = %s AND org_code = %s"""
            
            # Check if the record exists
            cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
            result = cur.fetchall()
            
            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                '''
                cur.execute(update_cost, (
                    total_equipment_cost, now, passed_data["wo_number"], passed_data["org_code"]))
                '''
                cur.execute(update_cost, (
                    total_equipment_cost,
                    now,
                    passed_data["wo_number"],
                    passed_data["org_code"]
                ))
            else:
                # Insert a new record
                '''
                cur.execute(insert_cost, (
                    passed_data["wo_number"], total_equipment_cost, now, passed_data["org_code"]))
                '''
                cur.execute(insert_cost, (
                    passed_data["wo_number"],
                    total_equipment_cost,
                    now,
                    passed_data["org_code"]
                ))

            recalc_totals = """
                UPDATE wo_cost_estimates
                SET
                    total_cost = (
                        COALESCE(materials_cost, 0) +
                        COALESCE(labor_cost, 0) +
                        COALESCE(equipment_cost, 0) +
                        COALESCE(overhead_cost, 0) +
                        COALESCE(contingency_fund, 0)
                    ) - COALESCE(discounts, 0),

                    total_cost_low = (
                        COALESCE(materials_cost_low, 0) +
                        COALESCE(labor_cost, 0) +
                        COALESCE(equipment_cost, 0) +
                        COALESCE(overhead_cost, 0) +
                        COALESCE(contingency_fund, 0)
                    ) - COALESCE(discounts, 0),

                    total_cost_avg = (
                        COALESCE(materials_cost_avg, 0) +
                        COALESCE(labor_cost, 0) +
                        COALESCE(equipment_cost, 0) +
                        COALESCE(overhead_cost, 0) +
                        COALESCE(contingency_fund, 0)
                    ) - COALESCE(discounts, 0),

                    mark_up_amount = (
                        (
                            COALESCE(materials_cost, 0) +
                            COALESCE(labor_cost, 0) +
                            COALESCE(equipment_cost, 0) +
                            COALESCE(overhead_cost, 0) +
                            COALESCE(contingency_fund, 0)
                        ) - COALESCE(discounts, 0)
                    ) * (COALESCE(mark_up_percent, 0) / 100),

                    mark_up_amount_low = (
                        (
                            COALESCE(materials_cost_low, 0) +
                            COALESCE(labor_cost, 0) +
                            COALESCE(equipment_cost, 0) +
                            COALESCE(overhead_cost, 0) +
                            COALESCE(contingency_fund, 0)
                        ) - COALESCE(discounts, 0)
                    ) * (COALESCE(mark_up_percent, 0) / 100),

                    mark_up_amount_avg = (
                        (
                            COALESCE(materials_cost_avg, 0) +
                            COALESCE(labor_cost, 0) +
                            COALESCE(equipment_cost, 0) +
                            COALESCE(overhead_cost, 0) +
                            COALESCE(contingency_fund, 0)
                        ) - COALESCE(discounts, 0)
                    ) * (COALESCE(mark_up_percent, 0) / 100),

                    gross_total_cost = (
                        (
                            COALESCE(materials_cost, 0) +
                            COALESCE(labor_cost, 0) +
                            COALESCE(equipment_cost, 0) +
                            COALESCE(overhead_cost, 0) +
                            COALESCE(contingency_fund, 0)
                        ) - COALESCE(discounts, 0)
                    ) * (1 + (COALESCE(mark_up_percent, 0) / 100)),

                    gross_total_cost_low = (
                        (
                            COALESCE(materials_cost_low, 0) +
                            COALESCE(labor_cost, 0) +
                            COALESCE(equipment_cost, 0) +
                            COALESCE(overhead_cost, 0) +
                            COALESCE(contingency_fund, 0)
                        ) - COALESCE(discounts, 0)
                    ) * (1 + (COALESCE(mark_up_percent, 0) / 100)),

                    gross_total_cost_avg = (
                        (
                            COALESCE(materials_cost_avg, 0) +
                            COALESCE(labor_cost, 0) +
                            COALESCE(equipment_cost, 0) +
                            COALESCE(overhead_cost, 0) +
                            COALESCE(contingency_fund, 0)
                        ) - COALESCE(discounts, 0)
                    ) * (1 + (COALESCE(mark_up_percent, 0) / 100))

                WHERE wo_number = %s AND org_code = %s
            """
            
            cur.execute(recalc_totals, (
                passed_data["wo_number"],
                passed_data["org_code"]
            ))

            conn.commit()

            # Close the database connection
            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            # Return success response with 201 status code
            return jsonify({"message": "Operation completed successfully", "result": "posted"}), 201

        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error", "details": str(e)}), 500


    #--- save work order design for standalone ----#
    @app.route('/postwodesign2', methods=['POST'])
    def postwodesign2():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()
            
            total_materials_cost = 0.00
            total_labor_cost = 0.00
            total_equipment_cost = 0.00
            
            #--- SAVING COMPATIBLE UNITS ---

            # SQL for checking if a record exists
            
            check_cu = """SELECT COUNT(*) AS count FROM sa_compatible_units 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            
            insert_cu = """INSERT INTO sa_compatible_units (wo_number, task_number, cu_code,            cu_type, quantity, created_datetime, org_code) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            
            update_cu = """UPDATE sa_compatible_units 
                        SET cu_type = %s, quantity = %s, created_datetime = %s 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
            
            # Process each selected CU
            for selected_cu in passed_data["selected_cus"]:
                cu_code = selected_cu.get("code")
                cu_type = selected_cu.get("type")
                quantity = selected_cu.get("quantity")
                org_code = selected_cu.get("org_code")

                # Check if the record exists
                cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_cu, (
                        cu_type, quantity, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_cu, (
                        passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                    ))
            
            # Create a temporary table for CU codes
            create_temp_table = """CREATE TEMPORARY TABLE temp_cu_codes (cu_code VARCHAR(255) NOT NULL)"""

            # Insert CU codes into the temporary table
            insert_into_temp = """INSERT INTO temp_cu_codes (cu_code) VALUES (%s)"""

            # Delete records not in the selected CU codes
            
            delete_cu = """DELETE FROM sa_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_cu_codes) AND org_code = %s"""
            
            # Execute: Create the temporary table
            cur.execute(create_temp_table)

            # Execute: Insert CU codes into the temporary table
            cu_codes = [cu["code"] for cu in passed_data["selected_cus"]]
            cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
            
            # Execute: Perform the DELETE operation
            cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

            
            #--- SAVING CU MATERIALS ---

            # SQL for checking if a record exists
            
            check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_items 
                            WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
            
            # SQL for inserting a new record
            
            insert_material = """INSERT INTO sa_task_physical_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                
            # SQL for updating an existing record
            
            update_material = """UPDATE sa_task_physical_items  
                                SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""

            # Process each selected material
            for selected_material in passed_data["selected_materials"]:
                cu_code = selected_material.get("cu_code")
                item_code = selected_material.get("item_code")
                quantity = selected_material.get("quantity")
                unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
                total_cost = float(quantity) * unit_cost
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_materials_cost = total_materials_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_matls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_matls_codes (cu_code, item_code) VALUES (%s, %s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM sa_task_physical_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_matls_codes) AND org_code = %s"""
            
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["cu_code"], material["item_code"])
                for material in passed_data["selected_materials"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            
            #--- SAVING CU ALTERATIONS ---
            
            insert_alteration = """INSERT INTO sa_cu_alterations (wo_number, cu_code, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
            
            for cu_alteration in passed_data["cu_alterations"]:
                cu_code = cu_alteration.get("cu_code")
                alteration = cu_alteration.get("alteration")
                
                # Insert a new record
                if alteration.strip() != "":
                    cur.execute(insert_alteration, (
                        passed_data["wo_number"], cu_code, alteration, now, passed_data["org_code"]
                    ))
            
            
            #--- SAVING CUSTOM MATERIALS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_custom_items 
                            WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

            # SQL for inserting a new record
            insert_material = """INSERT INTO sa_task_physical_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            # SQL for updating an existing record
            update_material = """UPDATE sa_task_physical_custom_items  
                                SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

            # Process each selected material
            for selected_material in passed_data["selected_custom_matls"]:
                item_code = selected_material.get("item_code")
                quantity = selected_material.get("quantity")
                unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
                total_cost = float(quantity) * unit_cost
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_materials_cost = total_materials_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_cmatls_codes (item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_cmatls_codes (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM sa_task_physical_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_cmatls_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["selected_custom_matls"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            

            #--- SAVING COST ESTIMATE ----
            
            # SQL for checking if a record exists
            check_cost = """SELECT COUNT(*) AS count FROM sa_cost_estimates 
                        WHERE wo_number = %s AND org_code = %s"""

            # SQL for inserting a new record
            insert_cost = """INSERT INTO sa_cost_estimates (
                            wo_number, 
                            materials_cost, 
                            total_cost, 
                            created_datetime, 
                            org_code
                            ) VALUES (
                                %s, 
                                %s, 
                                (
                                COALESCE(materials_cost, 0) + 
                                COALESCE(labor_cost, 0) + 
                                COALESCE(equipment_cost, 0) + 
                                COALESCE(overhead_cost, 0) + 
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0), 
                                %s, 
                                %s
                            )"""
                
            # SQL for updating an existing record
            update_cost = """UPDATE sa_cost_estimates  
                            SET 
                            materials_cost = %s, 
                            total_cost = (
                                COALESCE(materials_cost, 0) + 
                                COALESCE(labor_cost, 0) + 
                                COALESCE(equipment_cost, 0) + 
                                COALESCE(overhead_cost, 0) + 
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0), 
                            created_datetime = %s 
                            WHERE 
                                wo_number = %s 
                                AND org_code = %s"""

            # Check if the record exists
            cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
            result = cur.fetchall()
            

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cost, (
                    total_materials_cost, now, passed_data["wo_number"], passed_data["org_code"]))
            else:
                # Insert a new record
                cur.execute(insert_cost, (
                    passed_data["wo_number"], total_materials_cost, now, passed_data["org_code"]))
            
            
            #--- SAVING HUMAN COMPATIBLE UNITS ---

            # SQL for checking if a record exists
            check_cu = """SELECT COUNT(*) AS count FROM sa_human_compatible_units 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""

            # SQL for inserting a new record
            insert_cu = """INSERT INTO sa_human_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        
            # SQL for updating an existing record
            update_cu = """UPDATE sa_human_compatible_units 
                        SET cu_type = %s, quantity = %s, created_datetime = %s 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
            
            # Process each selected CU
            for selected_cu in passed_data["selected_human_cus"]:
                cu_code = selected_cu.get("code")
                cu_type = selected_cu.get("type")
                quantity = selected_cu.get("quantity")
                org_code = selected_cu.get("org_code")

                # Check if the record exists
                cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_cu, (
                        cu_type, quantity, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_cu, (
                        passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                    ))
                    
            # Create a temporary table for CU codes
            create_temp_table = """CREATE TEMPORARY TABLE temp_hcu_codes (cu_code VARCHAR(255) NOT NULL)"""

            # Insert CU codes into the temporary table
            insert_into_temp = """INSERT INTO temp_hcu_codes (cu_code) VALUES (%s)"""

            # Delete records not in the selected CU codes
            delete_cu = """DELETE FROM sa_human_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_hcu_codes) AND org_code = %s"""
            
            # Execute: Create the temporary table
            cur.execute(create_temp_table)

            # Execute: Insert CU codes into the temporary table
            cu_codes = [cu["code"] for cu in passed_data["selected_human_cus"]]
            cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
            
            # Execute: Perform the DELETE operation
            cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

            
            #--- SAVING HUMAN CU LABOR ITEMS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM sa_task_human_items 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO sa_task_human_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            # SQL for updating an existing record
            update_material = """UPDATE sa_task_human_items  
                                SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
            
            # Process each selected labor items
            for selected_material in passed_data["selected_labors"]:
                cu_code = selected_material.get("cu_code")
                item_code = selected_material.get("item_code")
                quantity = selected_material.get("quantity")
                unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
                total_cost = float(quantity) * unit_cost
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_labor_cost = total_labor_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_labors_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_labors_codes (cu_code, item_code) VALUES (%s, %s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM sa_task_human_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_labors_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["cu_code"], material["item_code"])
                for material in passed_data["selected_labors"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            
            #--- SAVING CU LABOR ALTERATIONS ---
            
            insert_alteration_labor = """INSERT INTO sa_cu_alterations (wo_number, cu_code, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
            
            for cu_alteration_labor in passed_data["cu_alterations_labor"]:
                cu_code_labor = cu_alteration_labor.get("cu_code")
                alteration_labor = cu_alteration_labor.get("alteration")
                
                # Insert a new record
                if alteration_labor.strip() != "":
                    cur.execute(insert_alteration_labor, (
                            passed_data["wo_number"], cu_code_labor, alteration_labor, now, passed_data["org_code"]
                    ))
            
            
            #--- SAVING CUSTOM LABOR ITEMS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM sa_task_human_custom_items 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO sa_task_human_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                
            # SQL for updating an existing record
            update_material = """UPDATE sa_task_human_custom_items  
                                SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""

            # Process each selected labor items
            for selected_material in passed_data["selected_custom_labors"]:
                item_code = selected_material.get("item_code")
                quantity = selected_material.get("quantity")
                unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
                total_cost = float(quantity) * unit_cost
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_labor_cost = total_labor_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_hcmatls_codes (item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_hcmatls_codes (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM sa_task_human_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_hcmatls_codes) AND org_code = %s"""
            
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["selected_custom_labors"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            
            #--- SAVING LABOR COST ESTIMATE ----
            
            # SQL for checking if a record exists
            check_cost = """SELECT COUNT(*) AS count FROM sa_cost_estimates 
                        WHERE wo_number = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            insert_cost = """INSERT INTO sa_cost_estimates (
                            wo_number, 
                            labor_cost, 
                            total_cost, 
                            created_datetime, 
                            org_code
                            ) VALUES (
                                %s, 
                                %s, 
                                (
                                COALESCE(materials_cost, 0) + 
                                COALESCE(labor_cost, 0) + 
                                COALESCE(equipment_cost, 0) + 
                                COALESCE(overhead_cost, 0) + 
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0), 
                                %s, 
                                %s
                            )"""

            # SQL for updating an existing record
            update_cost = """UPDATE sa_cost_estimates  
                            SET 
                            labor_cost = %s, 
                            total_cost = (
                                COALESCE(materials_cost, 0) + 
                                COALESCE(labor_cost, 0) + 
                                COALESCE(equipment_cost, 0) + 
                                COALESCE(overhead_cost, 0) + 
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0), 
                            created_datetime = %s 
                            WHERE 
                                wo_number = %s 
                                AND org_code = %s"""

            # Check if the record exists
            cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
            result = cur.fetchall()
            

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cost, (
                    total_labor_cost, now, passed_data["wo_number"], passed_data["org_code"]))
            else:
                # Insert a new record
                cur.execute(insert_cost, (
                    passed_data["wo_number"], total_labor_cost, now, passed_data["org_code"]))
            
            
            #--- SAVING EQUIPMENT COMPATIBLE UNITS ---

            # SQL for checking if a record exists
            check_cu = """SELECT COUNT(*) AS count FROM sa_equip_compatible_units 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            insert_cu = """INSERT INTO sa_equip_compatible_units (wo_number, task_number, cu_code, cu_type, quantity, created_datetime, org_code) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        
            # SQL for updating an existing record
            update_cu = """UPDATE sa_equip_compatible_units 
                        SET cu_type = %s, quantity = %s, created_datetime = %s 
                        WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND org_code = %s"""
            
            # Process each selected CU
            for selected_cu in passed_data["selected_equip_cus"]:
                cu_code = selected_cu.get("code")
                cu_type = selected_cu.get("type")
                quantity = selected_cu.get("quantity")
                org_code = selected_cu.get("org_code")

                # Check if the record exists
                cur.execute(check_cu, (passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_cu, (
                        cu_type, quantity, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_cu, (
                        passed_data["wo_number"], passed_data["task_number"], cu_code, cu_type, quantity, now, passed_data["org_code"]
                    ))
            
            # Create a temporary table for CU codes
            create_temp_table = """CREATE TEMPORARY TABLE temp_ecu_codes (cu_code VARCHAR(255) NOT NULL)"""

            # Insert CU codes into the temporary table
            insert_into_temp = """INSERT INTO temp_ecu_codes (cu_code) VALUES (%s)"""

            # Delete records not in the selected CU codes
            delete_cu = """DELETE FROM sa_equip_compatible_units WHERE wo_number = %s AND task_number = %s AND cu_code NOT IN (SELECT cu_code FROM temp_ecu_codes) AND org_code = %s"""
            
            # Execute: Create the temporary table
            cur.execute(create_temp_table)

            # Execute: Insert CU codes into the temporary table
            cu_codes = [cu["code"] for cu in passed_data["selected_equip_cus"]]
            cur.executemany(insert_into_temp, [(code,) for code in cu_codes])
            
            # Execute: Perform the DELETE operation
            cur.execute(delete_cu, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))

            
            #--- SAVING EQUIPMENT CU MATERIALS ---

            # SQL for checking if a record exists
            check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_equip_items 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO sa_task_physical_equip_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, cu_code, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            update_material = """UPDATE sa_task_physical_equip_items   
                                SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # Process each selected material
            for selected_material in passed_data["selected_equipment"]:
                cu_code = selected_material.get("cu_code")
                item_code = selected_material.get("item_code")
                quantity = selected_material.get("quantity")
                unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
                total_cost = float(quantity) * unit_cost
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_equipment_cost = total_equipment_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], cu_code, item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, cu_code, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_ematls_codes (cu_code VARCHAR(255) NOT NULL,item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_ematls_codes (cu_code, item_code) VALUES (%s, %s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM sa_task_physical_equip_items WHERE wo_number = %s AND task_number = %s AND CONCAT(cu_code, item_code) NOT IN (SELECT CONCAT(cu_code, item_code) FROM temp_ematls_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["cu_code"], material["item_code"])
                for material in passed_data["selected_equipment"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            
            
            #--- SAVING CU EQUIPMENT ALTERATIONS ---
            
            insert_alteration_equipment = """INSERT INTO sa_cu_alterations (wo_number, cu_code, alteration, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s)"""
            
            for cu_alteration_equipment in passed_data["cu_alterations_equipment"]:
                cu_code_equipment = cu_alteration_equipment.get("cu_code")
                alteration_equipment = cu_alteration_equipment.get("alteration")
                
                # Insert a new record
                if alteration_equipment.strip() != "":
                    cur.execute(insert_alteration_equipment, (
                            passed_data["wo_number"], cu_code_equipment, alteration_equipment, now, passed_data["org_code"]
                    ))
            
            
            #--- SAVING EQUIPMENT CUSTOM MATERIALS ---

            # SQL for checking if a record exists
            
            check_material = """SELECT COUNT(*) AS count FROM sa_task_physical_equip_custom_items 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting a new record
            insert_material = """INSERT INTO sa_task_physical_equip_custom_items (wo_number, task_number, item_code, quantity, uom, unit_cost, total_cost, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                
            # SQL for updating an existing record
            update_material = """UPDATE sa_task_physical_equip_custom_items  
                                SET quantity = %s, unit_cost = %s, total_cost = %s, created_datetime = %s 
                                WHERE wo_number = %s AND task_number = %s AND item_code = %s AND org_code = %s"""
                                
            # Process each selected material
            for selected_material in passed_data["selected_custom_equipment"]:
                item_code = selected_material.get("item_code")
                quantity = selected_material.get("quantity")
                unit_cost = float(selected_material.get("unit_cost").replace(",", ""))
                total_cost = float(quantity) * unit_cost
                uom = selected_material.get("uom")
                org_code = selected_material.get("org_code")
                total_equipment_cost = total_equipment_cost + total_cost
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (
                        quantity, unit_cost, total_cost, now, 
                        passed_data["wo_number"], passed_data["task_number"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["wo_number"], passed_data["task_number"], item_code, quantity, uom, unit_cost, total_cost, now, passed_data["org_code"]
                    ))

            # Create a temporary table for cu_code and item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_ecmatls_codes (item_code VARCHAR(255) NOT NULL)"""

            # Insert cu_code and item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_ecmatls_codes (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM sa_task_physical_equip_custom_items WHERE wo_number = %s AND task_number = %s AND item_code NOT IN (SELECT item_code FROM temp_ecmatls_codes) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["selected_custom_equipment"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["wo_number"], passed_data["task_number"], passed_data["org_code"]))
            

            #--- SAVING EQUIPMENT COST ESTIMATE ----
            
            # SQL for checking if a record exists
            check_cost = """SELECT COUNT(*) AS count FROM sa_cost_estimates 
                        WHERE wo_number = %s AND org_code = %s"""
                        
            # SQL for inserting a new record
            insert_cost = """INSERT INTO sa_cost_estimates (
                            wo_number, 
                            equipment_cost, 
                            total_cost, 
                            created_datetime, 
                            org_code
                            ) VALUES (
                                %s, 
                                %s, 
                                (
                                COALESCE(materials_cost, 0) + 
                                COALESCE(labor_cost, 0) + 
                                COALESCE(equipment_cost, 0) + 
                                COALESCE(overhead_cost, 0) + 
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0), 
                                %s, 
                                %s
                            )"""
                            
            # SQL for updating an existing record
            update_cost = """UPDATE sa_cost_estimates  
                            SET 
                            equipment_cost = %s, 
                            total_cost = (
                                COALESCE(materials_cost, 0) + 
                                COALESCE(labor_cost, 0) + 
                                COALESCE(equipment_cost, 0) + 
                                COALESCE(overhead_cost, 0) + 
                                COALESCE(contingency_fund, 0)
                                ) - COALESCE(discounts, 0), 
                            created_datetime = %s 
                            WHERE 
                                wo_number = %s 
                                AND org_code = %s"""
                                
            # Check if the record exists
            cur.execute(check_cost, (passed_data["wo_number"], passed_data["org_code"]))
            result = cur.fetchall()
            

            if result and "count" in result[0]:
                count = result[0]["count"]
                exists = count > 0
            else:
                exists = False

            if exists:
                # Update the existing record
                cur.execute(update_cost, (
                    total_equipment_cost, now, passed_data["wo_number"], passed_data["org_code"]))
            else:
                # Insert a new record
                cur.execute(insert_cost, (
                    passed_data["wo_number"], total_equipment_cost, now, passed_data["org_code"]))
            
            conn.commit()

            # Close the database connection
            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            # Return success response with 201 status code
            return jsonify({"message": "Operation completed successfully", "result": "posted"}), 201

        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error", "details": str(e)}), 500


    #--- save new work order ----#
    @app.route('/savenewworkorder', methods=['POST'])
    def savenewworkorder():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()

            next_wo_code = generate_next_wo_number(passed_data["wr_code"])
            
            # Insert into work order table
            sql1 = """INSERT INTO work_orders (wo_type, wo_description, status, project_name, project_description, business_unit, requested_by, priority_level, due_date, location, job_start_date, job_end_date, org_code, created_datetime, wr_id, wo_code, project_gid, task_gid) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            data1 = (
                passed_data["wo_type"], 
                passed_data["wo_description"], 
                passed_data["wo_status"], 
                passed_data["project_name"],
                passed_data["project_description"], 
                passed_data["business_unit"],
                passed_data["requested_by"],  
                passed_data["priority_level"], 
                passed_data["due_date"], 
                passed_data["location"], 
                passed_data["job_start_date"], 
                passed_data["job_end_date"], 
                passed_data["org_code"],
                now,
                passed_data["wr_id"],
                next_wo_code,
                passed_data.get("project_gid", ""),
                passed_data.get("task_gid", "")
            )
            cur.execute(sql1, data1)

            # Get the newly created work order number
            wo_number = cur.lastrowid

            # --- validation ---
            planners = passed_data.get("planners", [])
            valid_planners = [p for p in planners if str(p).strip()]

            pre_approver = passed_data.get("pre_approver", "")
            approver = passed_data.get("approver", "")

            if len(valid_planners) == 0:
                return jsonify({
                    "error": "At least one planner must be assigned to the work request."
                }), 400

            if not str(pre_approver).strip():
                return jsonify({
                    "error": "Pre-Approver is required."
                }), 400

            if not str(approver).strip():
                return jsonify({
                    "error": "Final Approver is required."
                }), 400

            # --- save selected planners / approvers to work_order_team ---
            insert_team = """
                INSERT INTO work_order_team
                (wo_number, user, role, assigned_datetime, org_code, wr_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """

            # planners
            for planner in valid_planners:
                cur.execute(insert_team, (
                    wo_number,
                    planner,
                    "planner",
                    now,
                    passed_data["org_code"],
                    None
                ))

            # pre-approver = team lead
            cur.execute(insert_team, (
                wo_number,
                pre_approver,
                "team lead",
                now,
                passed_data["org_code"],
                None
            ))

            # final approver = manager
            cur.execute(insert_team, (
                wo_number,
                approver,
                "manager",
                now,
                passed_data["org_code"],
                None
            ))


            # SQL for inserting into status change logs
            sql1 = """INSERT INTO status_changes (txn_type, txn_reference, previous_status, new_status, changed_by, change_reason, changed_on, source, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = ("Work Order", wo_number, "", passed_data["wo_status"], passed_data["requested_by"], "New work order", now, "Web App", passed_data["org_code"])
            
            cur.execute(sql1, data1)

            project_gid = passed_data.get("project_gid", "")
            task_gid    = passed_data.get("task_gid", "")

            if project_gid and task_gid:
                sql_chatbox = """
                    UPDATE app_chatbox
                    SET    wo_code = %s
                    WHERE  project_gid = %s
                    AND    task_gid    = %s
                """
                cur.execute(sql_chatbox, (next_wo_code, project_gid, task_gid))

            conn.commit()

            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            return jsonify({"message": "New work order created", "result": "inserted"}), 201

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    #--- save work order updates ----#
    @app.route('/updateworkorder', methods=['POST'])
    def updateworkorder():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()
            wo_number = passed_data["wo_number"]
            org_code = passed_data["org_code"]

            # Update the work order
            sql1 = """UPDATE work_orders 
                    SET wo_description = %s, project_name = %s, project_description = %s, business_unit = %s, priority_level = %s, due_date = %s, 
                        location = %s, job_start_date = %s, job_end_date = %s 
                    WHERE wo_number = %s AND org_code = %s"""
            
            data1 = (
                passed_data["wo_description"], 
                passed_data["project_name"],
                passed_data["project_description"],
                passed_data["business_unit"], 
                passed_data["priority_level"], 
                passed_data["due_date"], 
                passed_data["location"], 
                passed_data["job_start_date"], 
                passed_data["job_end_date"], 
                wo_number, 
                org_code
            )
            cur.execute(sql1, data1)

            planners = passed_data.get("planners", [])
            valid_planners = [p for p in planners if str(p).strip()]

            pre_approver = passed_data.get("pre_approver", "")
            approver = passed_data.get("approver", "")

            if len(valid_planners) == 0:
                raise Exception("At least one planner is required.")

            if not str(pre_approver).strip():
                raise Exception("Pre-Approver is required.")

            if not str(approver).strip():
                raise Exception("Final Approver is required.")

            sql_delete = """
            DELETE FROM work_order_team
            WHERE wo_number = %s
            AND org_code = %s
            AND role IN (%s,%s,%s)
            """

            cur.execute(sql_delete, (
                wo_number,
                org_code,
                "planner",
                "team lead",
                "manager"
            ))

            insert_team = """
            INSERT INTO work_order_team
            (
                wo_number,
                user,
                role,
                assigned_datetime,
                org_code
            )
            VALUES (%s,%s,%s,%s,%s)
            """

            for planner in valid_planners:
                cur.execute(insert_team, (
                    wo_number,
                    planner,
                    "planner",
                    now,
                    org_code
                ))

            cur.execute(insert_team, (
                wo_number,
                pre_approver,
                "team lead",
                now,
                org_code
            ))

            cur.execute(insert_team, (
                wo_number,
                approver,
                "manager",
                now,
                org_code
            ))

            conn.commit()

            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            return jsonify({"message": "Status updated", "result": "updated"}), 201

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new standalone master info ----#
    @app.route('/postsainfo', methods=['POST'])
    def postsainfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting work request data
            sql1 = """INSERT INTO standalone_designs (sa_description, created_datetime, planner, status, org_code) VALUES (%s, %s, %s, %s, %s)"""
            data1 = (passed_data["sa_description"], now, passed_data["planner"], "Open", passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            sa_number = cur.lastrowid
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": sa_number}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new work log master info ----#
    @app.route('/postwlinfo', methods=['POST'])
    def postwlinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting work request data
            sql1 = """INSERT INTO work_logs (email_address, title, log_datetime, status, org_code) VALUES (%s, %s, %s, %s, %s)"""
            data1 = (passed_data["email_address"], passed_data["title"], now, passed_data["status"], passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            wl_number = cur.lastrowid
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": wl_number}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save standalone master info updates ----#
    @app.route('/updatesainfo', methods=['POST'])
    def updatesainfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            wo_number = 0
            
            sql1 = """UPDATE standalone_designs SET sa_description = %s, planner = %s WHERE sa_number = %s AND org_code = %s"""
            
            data1 = (passed_data["sa_description"], passed_data["planner"], passed_data["sa_number"], passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Info updated", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save work log master info updates ----#
    @app.route('/updatewlinfo', methods=['POST'])
    def updatewlinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            wo_number = 0
            
            sql1 = """UPDATE work_logs SET title = %s WHERE id = %s AND org_code = %s"""
            
            data1 = (passed_data["title"], passed_data["id"], passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Info updated", "result": "updated"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new timesheet entry ----#
    @app.route('/posttimesheet', methods=['POST'])
    def posttimesheet():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting entries
            insert_entry = """INSERT INTO timesheets (work_log_id, email_address, task, start, end, hours, created_datetime, org_code, task_type, wo_code, activities, remarks) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            # Process entries array
            for entry in passed_data["entries"]:
                tasktitle = entry.get("task")
                task_start = entry.get("start")
                task_end = entry.get("end")
                
                task_type = entry.get("task_type")
                wo_code = entry.get("wo_code")
                activities = entry.get("activities")
                remarks = entry.get("remarks")

                duration_str = entry.get("duration") 
                 # e.g., "24h 0m" or "2h 30m"
        
                # Use regex to extract hours and minutes
                hours_match = re.search(r"(\d+)\s*h", duration_str)
                minutes_match = re.search(r"(\d+)\s*m", duration_str)
                
                if hours_match:
                    hours = Decimal(hours_match.group(1))
                else:
                    hours = Decimal("0")
                
                if minutes_match:
                    minutes = Decimal(minutes_match.group(1))
                else:
                    minutes = Decimal("0")
                
                # Convert minutes to hours
                minutes_as_hours = minutes / Decimal("60")
                task_hrs = hours + minutes_as_hours
                
                cur.execute(insert_entry, (passed_data["work_log_id"], passed_data["email_address"], tasktitle, task_start, task_end, task_hrs, now, passed_data["org_code"], task_type, wo_code, activities, remarks))

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Timesheet Entries created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500

    #--- save new timesheet entry per user ----#
    @app.route('/posttimesheet_user', methods=['POST'])
    def posttimesheet_user():
        passed_data = request.get_json(force=True)

        if 'org_code' not in passed_data:
            return jsonify({'error': 'org_code is required'}), 400
        if 'email_address' not in passed_data:
            return jsonify({'error': 'email_address is required'}), 400
        if 'entries' not in passed_data:
            return jsonify({'error': 'entries is required'}), 400

        org_code = passed_data['org_code']
        email_address = passed_data['email_address'].strip()
        entries = passed_data['entries']

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                INSERT INTO timesheets
                (email_address, task, start, end, hours, created_datetime, org_code,
                task_type, wo_code, activities, remarks)
                VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s)
            """

            for e in entries:
                task = (e.get('task') or '').strip()
                task_type = (e.get('task_type') or 'Admin Task').strip()
                wo_code = (e.get('wo_code') or '').strip()
                start = e.get('start')
                end = e.get('end')
                activities = (e.get('activities') or '').strip()
                remarks = (e.get('remarks') or '').strip()

                # hours can be computed by backend or sent by client
                hours = e.get('hours')

                # If hours not provided, compute from start/end
                if (hours is None or str(hours).strip() == "") and start and end:
                    # start/end expected ISO strings
                    from datetime import datetime
                    sdt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    edt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    diff = (edt - sdt).total_seconds() / 3600.0
                    hours = round(diff, 2) if diff > 0 else 0

                cur.execute(sql, (
                    email_address,
                    task,
                    start,
                    end,
                    hours,
                    org_code,
                    task_type,
                    wo_code,
                    activities,
                    remarks
                ))

            conn.commit()
            return jsonify({'result': 'inserted'}), 201

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            print("posttimesheet_user error:", e)
            return jsonify({'error': str(e)}), 500


    # --- update timesheet entry ---
    '''
    @app.route('/updatetimesheet', methods=['POST'])
    def update_timesheet():
        try:
            data = request.get_json()

            required_fields = [
                'id', 'start', 'end', 'hours',
                'task', 'task_type', 'wo_code',
                'activities', 'remarks', 'org_code'
            ]

            for f in required_fields:
                if f not in data:
                    return jsonify({'error': f'Missing field: {f}'}), 400

            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                UPDATE timesheets
                SET
                    start = %s,
                    end = %s,
                    hours = %s,
                    task = %s,
                    task_type = %s,
                    wo_code = %s,
                    activities = %s,
                    remarks = %s
                WHERE
                    id = %s
                    AND org_code = %s
            """

            values = (
                data['start'],
                data['end'],
                data['hours'],
                data['task'],
                data['task_type'],
                data['wo_code'],
                data['activities'],
                data['remarks'],
                data['id'],
                data['org_code'],
            )

            cur.execute(sql, values)
            conn.commit()

            return jsonify({'result': 'updated'}), 200

        except Exception as e:
            print("update_timesheet error:", e)
            return jsonify({'error': str(e)}), 500

    # --- update timesheet entry ---
    @app.route('/updatetimeentry', methods=['POST'])
    def updatetimeentry():
        passed_data = request.get_json(force=True)

        if 'org_code' not in passed_data:
            return jsonify({'error': 'org_code is required'}), 400
        if 'id' not in passed_data:
            return jsonify({'error': 'id is required'}), 400

        org_code = passed_data['org_code']
        entry_id = passed_data['id']

        task = (passed_data.get('task') or '').strip()
        task_type = (passed_data.get('task_type') or 'Admin Task').strip()
        wo_code = (passed_data.get('wo_code') or '').strip()
        start = passed_data.get('start')
        end = passed_data.get('end')
        activities = (passed_data.get('activities') or '').strip()
        remarks = (passed_data.get('remarks') or '').strip()
        email_address = (passed_data.get('email_address') or '').strip()

        # hours sent by client (recommended), fallback compute if blank
        hours = passed_data.get('hours')

        try:
            if (hours is None or str(hours).strip() == "") and start and end:
                from datetime import datetime
                sdt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                edt = datetime.fromisoformat(end.replace("Z", "+00:00"))
                diff = (edt - sdt).total_seconds() / 3600.0
                hours = round(diff, 2) if diff > 0 else 0

            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                UPDATE timesheets
                SET
                    task = %s,
                    task_type = %s,
                    wo_code = %s,
                    start = %s,
                    end = %s,
                    hours = %s,
                    activities = %s,
                    remarks = %s
                WHERE id = %s
                AND org_code = %s
            """

            cur.execute(sql, (
                task,
                task_type,
                wo_code,
                start,
                end,
                hours,
                activities,
                remarks,
                entry_id,
                org_code
            ))

            conn.commit()
            return jsonify({'result': 'updated'}), 200

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            print("updatetimeentry error:", e)
            return jsonify({'error': str(e)}), 500
    '''
    # --- update timesheet entry (CONSOLIDATED + MySQL SAFE) ---
    @app.route('/updatetimeentry', methods=['POST'])
    def updatetimeentry():
        passed_data = request.get_json(force=True) or {}

        logger.info(passed_data)

        if 'org_code' not in passed_data:
            return jsonify({'error': 'org_code is required'}), 400
        if 'id' not in passed_data:
            return jsonify({'error': 'id is required'}), 400

        org_code = (passed_data.get('org_code') or '').strip()
        entry_id = passed_data.get('id')

        try:
            entry_id = int(entry_id)
        except:
            return jsonify({'error': 'id must be an integer'}), 400

        # ---- helpers ----
        def opt_str(key):
            # return None if key absent (so it won't overwrite)
            if key not in passed_data:
                return None
            v = passed_data.get(key)
            return '' if v is None else str(v).strip()

        def opt_num(key):
            if key not in passed_data:
                return None
            v = passed_data.get(key)
            if v is None:
                return None
            s = str(v).strip()
            if s == "":
                return None
            try:
                return float(s)
            except:
                return None

        def opt_dt(key):
            # Return:
            # - None if key absent (do not update)
            # - datetime object if present & parseable
            if key not in passed_data:
                return None
            v = passed_data.get(key)
            if v is None:
                return None
            raw = str(v).strip()
            if raw == "":
                return None

            # ISO like: 2026-01-28T10:20:00.000Z
            try:
                s = raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                # make it naive for MySQL DATETIME (store as local or server-time)
                if dt.tzinfo is not None:
                    dt = dt.astimezone().replace(tzinfo=None)
                return dt
            except:
                pass

            # RFC1123 like: Wed, 24 Dec 2025 12:54:00 GMT
            try:
                dt = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S GMT")
                return dt
            except:
                pass

            # last resort: try "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
                return dt
            except:
                return None

        # ---- incoming optional fields ----
        task = opt_str('task')
        task_type = opt_str('task_type')
        wo_code = opt_str('wo_code')
        start_in = opt_dt('start')
        end_in = opt_dt('end')
        activities = opt_str('activities')
        remarks = opt_str('remarks')
        email_address = opt_str('email_address')  # optional ownership filter

        # hours optional; if absent -> compute if possible
        hours_in = opt_num('hours')

        conn = None
        cur = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            # Get existing (for computing hours if needed)
            cur.execute("""
                SELECT `start`, `end`, `hours`, `email_address`
                FROM timesheets
                WHERE id = %s AND org_code = %s
            """, (entry_id, org_code))
            row = cur.fetchone()

            if not row:
                return jsonify({'error': 'Timesheet entry not found'}), 404

            existing_start, existing_end, existing_hours, existing_email = row

            # Ownership check (only if caller sends email_address)
            if email_address is not None and email_address.strip() != "":
                if (existing_email or "").strip().lower() != email_address.strip().lower():
                    return jsonify({'error': 'Not allowed (email mismatch)'}), 403

            final_start = start_in if start_in is not None else existing_start
            final_end = end_in if end_in is not None else existing_end

            hours_to_set = hours_in
            if hours_to_set is None and final_start and final_end:
                diff = (final_end - final_start).total_seconds() / 3600.0
                hours_to_set = round(diff, 2) if diff > 0 else 0

            # Build dynamic UPDATE so we only update provided fields
            sets = []
            params = []

            if task is not None:
                sets.append("task = %s")
                params.append(task)

            if task_type is not None:
                sets.append("task_type = %s")
                params.append(task_type)

            if wo_code is not None:
                sets.append("wo_code = %s")
                params.append(wo_code)

            if start_in is not None:
                sets.append("`start` = %s")
                params.append(start_in)

            if end_in is not None:
                sets.append("`end` = %s")
                params.append(end_in)

            # hours: update if computed OR caller provided OR start/end changed
            # (This guarantees hours stays consistent when editing times.)
            if hours_to_set is not None:
                sets.append("hours = %s")
                params.append(hours_to_set)

            if activities is not None:
                sets.append("activities = %s")
                params.append(activities)

            if remarks is not None:
                sets.append("remarks = %s")
                params.append(remarks)

            if not sets:
                return jsonify({'error': 'Nothing to update'}), 400

            sql = f"""
                UPDATE timesheets
                SET {", ".join(sets)}
                WHERE id = %s AND org_code = %s
            """
            params.extend([entry_id, org_code])

            cur.execute(sql, tuple(params))
            conn.commit()

            return jsonify({'result': 'updated'}), 200

        except Exception as e:
            try:
                if conn:
                    conn.rollback()
            except:
                pass
            return jsonify({'error': str(e)}), 500

        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except:
                pass


    #--- save new supplier ----#
    @app.route('/postnewsupplier', methods=['POST'])
    def postnewsupplier():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting supplier data
            sql1 = """INSERT INTO suppliers (name, primary_contact, contact_numbers, email_address, website, office_address, tax_identification_number, payment_terms, credit_limit_terms, industry, created_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["name"], passed_data["primary_contact"], passed_data["contact_numbers"], passed_data["email_address"], passed_data["website"], passed_data["office_address"], passed_data["tin"], passed_data["payment_terms"], passed_data["credit_limit_terms"], passed_data["industry"], now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            supplier_id = cur.lastrowid
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new material ----#
    @app.route('/postnewmaterial', methods=['POST'])
    def postnewmaterial():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting supplier data
            sql1 = """INSERT INTO physical_items (description, brand, supplier, source, year, unit_cost, unit_cost_low, unit_cost_avg, category, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["description"], passed_data["brand"], passed_data["supplier"], passed_data["source"], passed_data["year"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["category"], passed_data["uom"], 1, now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            supplier_id = cur.lastrowid
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new labor ----#
    @app.route('/postnewlabor', methods=['POST'])
    def postnewlabor():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting supplier data
            sql1 = """INSERT INTO human_items (description, unit_cost, unit_cost_low, unit_cost_avg, category, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["category"], passed_data["uom"], 1, now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            supplier_id = cur.lastrowid
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new equipment ----#
    @app.route('/postnewequipment', methods=['POST'])
    def postnewequipment():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting supplier data
            sql1 = """INSERT INTO physical_equip_items (description, unit_cost, unit_cost_low, unit_cost_avg, category, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["category"], passed_data["uom"], 1, now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
            
            # Get the newly created work request id
            supplier_id = cur.lastrowid
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new Material CU ----#
    @app.route('/postnewmaterialcu', methods=['POST'])
    def postnewmaterialcu():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()

            cu_code = get_next_cu_code("MAT")
            
            # SQL for inserting supplier data
            sql1 = """INSERT INTO physical_compatible_units (code, title, description, quantity, type, category, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (cu_code, passed_data["title"], passed_data["description"], 1, 'M',passed_data["category"], 1, now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new Labor CU ----#
    @app.route('/postnewlaborcu', methods=['POST'])
    def postnewlaborcu():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()

            cu_code = get_next_cu_code("LAB")
            
            # SQL for inserting supplier data
            sql1 = """INSERT INTO human_compatible_units (code, title, description, quantity, type, category, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (cu_code, passed_data["title"], passed_data["description"], 1, 'L',passed_data["category"], 1, now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    #--- save new Equipment CU ----#
    @app.route('/postnewequipmentcu', methods=['POST'])
    def postnewequipmentcu():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()

            cu_code = get_next_cu_code("EQU")
            
            # SQL for inserting supplier data
            sql1 = """INSERT INTO physical_equip_compatible_units (code, title, description, quantity, type, category, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            data1 = (cu_code, passed_data["title"], passed_data["description"], 1, 'E',passed_data["category"], 1, now, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new material CU category ----#
    @app.route('/postnewmaterialcucategory', methods=['POST'])
    def postnewmaterialcucategory():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()

            cucat_code = get_next_cu_category_code()
            
            # SQL for inserting category data
            sql1 = """INSERT INTO physical_cu_categories (category, title, status, org_code) VALUES (%s, %s, %s, %s)"""
            data1 = (cucat_code, passed_data["category_title"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new labor CU category ----#
    @app.route('/postnewlaborcucategory', methods=['POST'])
    def postnewlaborcucategory():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()

            cucat_code = get_next_cu_category_code()
            
            # SQL for inserting category data
            sql1 = """INSERT INTO human_cu_categories (category, title, status, org_code) VALUES (%s, %s, %s, %s)"""
            data1 = (cucat_code, passed_data["category_title"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new equipment CU category ----#
    @app.route('/postnewequipmentcucategory', methods=['POST'])
    def postnewequipmentcucategory():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()

            cucat_code = get_next_cu_category_code()
            
            # SQL for inserting category data
            sql1 = """INSERT INTO equip_cu_categories (category, title, status, org_code) VALUES (%s, %s, %s, %s)"""
            data1 = (cucat_code, passed_data["category_title"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new material item category ----#
    @app.route('/postnewmaterialitemcategory', methods=['POST'])
    def postnewmaterialitemcategory():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting category data
            sql1 = """INSERT INTO physical_item_categories (description, status, org_code) VALUES (%s, %s, %s)"""
            data1 = (passed_data["category_title"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new labor item category ----#
    @app.route('/postnewlaboritemcategory', methods=['POST'])
    def postnewlaboritemcategory():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting category data
            sql1 = """INSERT INTO human_item_categories (description, status, org_code) VALUES (%s, %s, %s)"""
            data1 = (passed_data["category_title"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new equipment item category ----#
    @app.route('/postnewequipmentitemcategory', methods=['POST'])
    def postnewequipmentitemcategory():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting category data
            sql1 = """INSERT INTO equip_item_categories (description, status, org_code) VALUES (%s, %s, %s)"""
            data1 = (passed_data["category_title"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    #--- save new business unit ----#
    @app.route('/postnewbusinessunit', methods=['POST'])
    def postnewbusinessunit():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()

            bu_code = get_next_business_unit_code()
            
            # SQL for inserting row
            sql1 = """INSERT INTO business_units (code, description, acronym, status, org_code) VALUES (%s, %s, %s, %s, %s)"""
            data1 = (bu_code, passed_data["description"], passed_data["acronym"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save new planner ----#
    @app.route('/postnewplanner', methods=['POST'])
    def postnewplanner():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting row
            sql1 = """INSERT INTO planners (name, email_address, status, org_code) VALUES (%s, %s, %s, %s)"""
            data1 = (passed_data["name"], passed_data["email_address"], 1, passed_data["org_code"])
            
            cur.execute(sql1, data1)
                    
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "New Record created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    #--- save assigned materials entry ----#
    @app.route('/postassignedmaterials', methods=['POST'])
    def postassignedmaterials():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            check_material = """SELECT COUNT(*) AS count FROM supplier_materials 
                                WHERE supplier_id = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting materials
            insert_material = """INSERT INTO supplier_materials (supplier_id, item_code, created_datetime, org_code) VALUES (%s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            update_material = """UPDATE supplier_materials   
                                SET created_datetime = %s 
                                WHERE supplier_id = %s AND item_code = %s AND org_code = %s"""

            # Process assigned materials array
            for material in passed_data["assigned_materials"]:
                item_code = material.get("item_code")
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["supplier_id"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (now, 
                        passed_data["supplier_id"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["supplier_id"], item_code, now, passed_data["org_code"]
                    ))

            # Create a temporary table for item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

            # Insert item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM supplier_materials WHERE supplier_id = %s AND  item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["assigned_materials"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["supplier_id"], passed_data["org_code"]))
                
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Materials assignment created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save CU assigned materials entry ----#
    @app.route('/postcuassignedmaterials', methods=['POST'])
    def postcuassignedmaterials():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            check_material = """SELECT COUNT(*) AS count FROM physical_cu_items 
                                WHERE cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting materials
            insert_material = """INSERT INTO physical_cu_items (cu_code, item_code, quantity, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            update_material = """UPDATE physical_cu_items 
                                SET quantity = %s, updated_datetime = %s 
                                WHERE cu_code = %s AND item_code = %s AND org_code = %s"""

            
            # Process assigned materials array
            for material in passed_data["assigned_materials"]:
                item_code = material.get("item_code")
                quantity = material.get("quantity")
                uom = material.get("uom")
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["cu_code"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (quantity, now, 
                        passed_data["cu_code"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["cu_code"], item_code, quantity, uom, 1, now, passed_data["org_code"]
                    ))

            # Create a temporary table for item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

            # Insert item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM physical_cu_items WHERE cu_code = %s AND item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["assigned_materials"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["cu_code"], passed_data["org_code"]))
                
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Materials assignment created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save CU assigned labors entry ----#
    @app.route('/postcuassignedlabors', methods=['POST'])
    def postcuassignedlabors():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            check_material = """SELECT COUNT(*) AS count FROM human_cu_items 
                                WHERE cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting materials
            insert_material = """INSERT INTO human_cu_items (cu_code, item_code, quantity, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            update_material = """UPDATE human_cu_items 
                                SET quantity = %s, updated_datetime = %s 
                                WHERE cu_code = %s AND item_code = %s AND org_code = %s"""

            
            # Process assigned materials array
            for material in passed_data["assigned_materials"]:
                item_code = material.get("item_code")
                quantity = material.get("quantity")
                uom = material.get("uom")
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["cu_code"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (quantity, now, 
                        passed_data["cu_code"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["cu_code"], item_code, quantity, uom, 1, now, passed_data["org_code"]
                    ))

            # Create a temporary table for item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

            # Insert item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM human_cu_items WHERE cu_code = %s AND item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["assigned_materials"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["cu_code"], passed_data["org_code"]))
                
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Labors assignment created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- save CU assigned equipment entry ----#
    @app.route('/postcuassignedequipment', methods=['POST'])
    def postcuassignedequipment():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            check_material = """SELECT COUNT(*) AS count FROM physical_equip_cu_items 
                                WHERE cu_code = %s AND item_code = %s AND org_code = %s"""
                                
            # SQL for inserting materials
            insert_material = """INSERT INTO physical_equip_cu_items (cu_code, item_code, quantity, unit_of_measure, status, updated_datetime, org_code) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            
            # SQL for updating an existing record
            update_material = """UPDATE physical_equip_cu_items 
                                SET quantity = %s, updated_datetime = %s 
                                WHERE cu_code = %s AND item_code = %s AND org_code = %s"""

            
            # Process assigned materials array
            for material in passed_data["assigned_materials"]:
                item_code = material.get("item_code")
                quantity = material.get("quantity")
                uom = material.get("uom")
                
                # Check if the record exists
                cur.execute(check_material, (passed_data["cu_code"], item_code, passed_data["org_code"]))
                result = cur.fetchall()

                if result and "count" in result[0]:
                    count = result[0]["count"]
                    exists = count > 0
                else:
                    exists = False

                if exists:
                    # Update the existing record
                    cur.execute(update_material, (quantity, now, 
                        passed_data["cu_code"], item_code, passed_data["org_code"]
                    ))
                else:
                    # Insert a new record
                    cur.execute(insert_material, (
                        passed_data["cu_code"], item_code, quantity, uom, 1, now, passed_data["org_code"]
                    ))

            # Create a temporary table for item_code
            create_temp_table = """CREATE TEMPORARY TABLE temp_matls_assigns (item_code INT NOT NULL)"""

            # Insert item_code into the temporary table
            insert_into_temp = """INSERT INTO temp_matls_assigns (item_code) VALUES (%s)"""

            # Delete records not in the selected item codes
            delete_item = """DELETE FROM physical_equip_cu_items WHERE cu_code = %s AND item_code NOT IN (SELECT item_code FROM temp_matls_assigns) AND org_code = %s"""
                
            # Create the temporary table
            cur.execute(create_temp_table)

            # Prepare data for insertion
            item_codes = [
                (material["item_code"])
                for material in passed_data["assigned_materials"]
            ]

            # Insert data into the temporary table
            cur.executemany(insert_into_temp, item_codes)
            
            # Perform the DELETE operation
            cur.execute(delete_item, (passed_data["cu_code"], passed_data["org_code"]))
                
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Equipment assignment created successfully", "result": "inserted"}), 201
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- delete timesheet entry ----#
    @app.route('/deletetimeentry', methods=['DELETE'])
    def deletetimeentry():
        if 'row_id' in request.args:
            row_id = request.args['row_id']
        else:
            return "Error: No Row ID field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()
            
            # SQL for inserting entries
            delete_entry = """DELETE FROM timesheets WHERE id = %s AND org_code = %s"""
            cur.execute(delete_entry, (row_id, org_code))

            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 201 status code
            return jsonify({"message": "Time Entry deleted successfully", "result": "deleted"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # Saving changes on user roles list
    @app.route('/saveuserroleslist', methods=['PUT'])
    def saveuserroleslist():
        import traceback

        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            user_name = passed_data.get('user_name')
            roles_list = passed_data.get('roles_list')   # can be []
            org_code = passed_data.get('org_code')

            # ✅ allow empty list; only reject if roles_list is missing entirely
            if not user_name or roles_list is None or not org_code:
                return jsonify({"error": "Missing required fields"}), 400

            # Normalize roles
            new_roles = [r.get('role') for r in roles_list if r.get('role')]

            # Get existing roles
            cur.execute("""
                SELECT role FROM app_user_roles
                WHERE `user` = %s AND org_code = %s
            """, (user_name, org_code))

            existing_roles = [row['role'] for row in cur.fetchall()]

            # ✅ If no roles selected, delete ALL existing roles for that user/org
            if len(new_roles) == 0:
                cur.execute("""
                    DELETE FROM app_user_roles
                    WHERE `user` = %s AND org_code = %s
                """, (user_name, org_code))

                conn.commit()
                cur.close()
                conn.close()
                return jsonify({"message": "Updated successfully", "result": "updated"}), 200

            # Delete roles not in new list
            roles_to_delete = list(set(existing_roles) - set(new_roles))
            if roles_to_delete:
                placeholders = ','.join(['%s'] * len(roles_to_delete))
                delete_query = f"""
                    DELETE FROM app_user_roles
                    WHERE `user` = %s AND org_code = %s AND role IN ({placeholders})
                """
                params = (user_name, org_code) + tuple(roles_to_delete)
                cur.execute(delete_query, params)

            # Insert new roles
            roles_to_insert = list(set(new_roles) - set(existing_roles))
            insert_query = """
                INSERT INTO app_user_roles (`user`, role, status, org_code)
                VALUES (%s, %s, %s, %s)
            """
            for role in roles_to_insert:
                cur.execute(insert_query, (user_name, role, 1, org_code))

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({"message": "Updated successfully", "result": "updated"}), 200

        except Exception as e:
            logger.error(f"Error saving user roles: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"error": "Internal server error"}), 500


    # Activate / Deactivate user
    @app.route('/updateuserstatus', methods=['PUT'])
    def updateuserstatus():
        import traceback

        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            user_name = passed_data.get('user_name')
            status = passed_data.get('status')  # 1 = active, 0 = inactive
            org_code = passed_data.get('org_code')

            if user_name is None or status is None or org_code is None:
                return jsonify({"error": "Missing required fields"}), 400

            cur.execute("""
                UPDATE app_users
                SET status = %s
                WHERE `user` = %s
                AND org_code = %s
            """, (status, user_name, org_code))

            conn.commit()

            cur.close()
            conn.close()

            return jsonify({
                "message": "User status updated successfully",
                "result": "updated"
            }), 200

        except Exception as e:
            logger.error(f"Error updating user status: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"error": "Internal server error"}), 500
    
    
    # Update user info (name fields only for now; username is immutable)
    '''
    @app.route('/updateuserinfo', methods=['PUT'])
    def updateuserinfo():
        import traceback
        passed_data = request.get_json() or {}

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()  # if this is NOT a DictCursor, we handle below

            org_code = str(passed_data.get('org_code') or '').strip()
            user_id = str(passed_data.get('id') or '').strip()          # ✅ cast to str first
            user_name = str(passed_data.get('user') or '').strip()
            firstname = str(passed_data.get('firstname') or '').strip()
            lastname = str(passed_data.get('lastname') or '').strip()

            if not org_code or not user_id or not user_name:
                return jsonify({"error": "Missing required fields"}), 400

            # ✅ FIXED SQL (removed trailing comma before WHERE)
            cur.execute("""
                UPDATE app_users
                SET firstname = %s,
                    lastname = %s
                WHERE id = %s
                AND `user` = %s
                AND org_code = %s
            """, (firstname, lastname, user_id, user_name, org_code))

            conn.commit()

            # return updated record (for UI refresh)
            cur.execute("""
                SELECT id, `user`, firstname, lastname, status, org_code
                FROM app_users
                WHERE id = %s AND org_code = %s
                LIMIT 1
            """, (user_id, org_code))

            row = cur.fetchone()

            cur.close()
            conn.close()

            if not row:
                return jsonify({"error": "User not found"}), 404

            # ✅ handle BOTH DictCursor and normal tuple cursor
            if isinstance(row, dict):
                row['id'] = str(row.get('id'))
                return jsonify({"message": "User updated", "result": row}), 200
            else:
                # tuple fallback (id, user, firstname, lastname, status, org_code)
                result = {
                    "id": str(row[0]),
                    "user": row[1],
                    "firstname": row[2],
                    "lastname": row[3],
                    "status": row[4],
                    "org_code": row[5],
                }
                return jsonify({"message": "User updated", "result": result}), 200

        except Exception as e:
            logger.error(f"Error updating user info: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"error": "Internal server error"}), 500
    '''
    # Update user info
    @app.route('/updateuserinfo', methods=['PUT'])
    def updateuserinfo():
        import traceback
        import base64

        passed_data = request.get_json() or {}

        conn = None
        cur = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            org_code = str(passed_data.get('org_code') or '').strip()
            user_id = str(passed_data.get('id') or '').strip()
            user_name = str(passed_data.get('user') or '').strip()
            firstname = str(passed_data.get('firstname') or '').strip()
            lastname = str(passed_data.get('lastname') or '').strip()
            position_title = str(passed_data.get('position_title') or '').strip()
            signature_file_base64 = passed_data.get('signature_file_base64') or ''

            if not org_code or not user_id or not user_name:
                return jsonify({"error": "Missing required fields"}), 400

            signature_bytes = None

            if signature_file_base64:
                # supports both raw base64 and data:image/png;base64,...
                if ',' in signature_file_base64:
                    signature_file_base64 = signature_file_base64.split(',', 1)[1]

                signature_bytes = base64.b64decode(signature_file_base64)

                cur.execute("""
                    UPDATE app_users
                    SET firstname = %s,
                        lastname = %s,
                        position_title = %s,
                        signature_file = %s
                    WHERE id = %s
                    AND `user` = %s
                    AND org_code = %s
                """, (
                    firstname,
                    lastname,
                    position_title,
                    signature_bytes,
                    user_id,
                    user_name,
                    org_code
                ))
            else:
                cur.execute("""
                    UPDATE app_users
                    SET firstname = %s,
                        lastname = %s,
                        position_title = %s
                    WHERE id = %s
                    AND `user` = %s
                    AND org_code = %s
                """, (
                    firstname,
                    lastname,
                    position_title,
                    user_id,
                    user_name,
                    org_code
                ))

            conn.commit()

            cur.execute("""
                SELECT
                    id,
                    `user`,
                    firstname,
                    lastname,
                    position_title,
                    status,
                    org_code,
                    CASE WHEN signature_file IS NOT NULL THEN 1 ELSE 0 END AS has_signature
                FROM app_users
                WHERE id = %s
                AND org_code = %s
                LIMIT 1
            """, (user_id, org_code))

            row = cur.fetchone()

            if not row:
                return jsonify({"error": "User not found"}), 404

            if isinstance(row, dict):
                result = {
                    "id": str(row.get("id")),
                    "user": row.get("user"),
                    "firstname": row.get("firstname"),
                    "lastname": row.get("lastname"),
                    "position_title": row.get("position_title"),
                    "status": row.get("status"),
                    "org_code": row.get("org_code"),
                    "has_signature": row.get("has_signature"),
                }
            else:
                result = {
                    "id": str(row[0]),
                    "user": row[1],
                    "firstname": row[2],
                    "lastname": row[3],
                    "position_title": row[4],
                    "status": row[5],
                    "org_code": row[6],
                    "has_signature": row[7],
                }

            return jsonify({
                "message": "User updated",
                "result": result
            }), 200

        except Exception as e:
            if conn:
                conn.rollback()

            logger.error(f"Error updating user info: {str(e)}")
            logger.error(traceback.format_exc())

            return jsonify({
                "error": "Internal server error",
                "details": str(e)
            }), 500

        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except:
                pass

    # update app user FCM token
    @app.route('/savefcmtoken', methods=['PUT'])
    def savefcmtoken():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE app_users SET fcm_token = %s WHERE user = %s AND org_code = %s"""
            data1 = (passed_data["fcm_token"], passed_data["user_id"], passed_data["org_code"])  
            
            cur.execute(sql1, data1)
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update customer info change
    @app.route('/updatecustomer', methods=['PUT'])
    def updatecustomer():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE customers SET firstname = %s, middlename = %s, lastname = %s, email_address = %s, contact_number = %s, street_address = %s, city = %s, province = %s, company_name = %s, created_datetime = %s WHERE id = %s AND org_code = %s"""
            data1 = (passed_data["firstname"], passed_data["middlename"], passed_data["lastname"], passed_data["email_address"], passed_data["contact_number"], passed_data["street_address"], passed_data["city"], passed_data["province"], passed_data["company_name"], now, passed_data["id"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update supplier info change
    @app.route('/updatesupplier', methods=['PUT'])
    def updatesupplier():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE suppliers SET name = %s, primary_contact = %s, contact_numbers = %s, email_address = %s, website = %s, office_address = %s, tax_identification_number = %s, payment_terms = %s, credit_limit_terms = %s, industry = %s, created_datetime = %s WHERE id = %s AND org_code = %s"""
            data1 = (passed_data["name"], passed_data["primary_contact"], passed_data["contact_numbers"], passed_data["email_address"], passed_data["website"], passed_data["office_address"], passed_data["tin"], passed_data["payment_terms"], passed_data["credit_limit_terms"], passed_data["industry"], now, passed_data["id"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update material info change
    @app.route('/updatematerial', methods=['PUT'])
    def updatematerial():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE physical_items SET description = %s, brand = %s, supplier = %s, source = %s, year = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, unit_of_measure = %s, category = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
            data1 = (passed_data["description"], passed_data["brand"], passed_data["supplier"], passed_data["source"], passed_data["year"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["unit_of_measure"], passed_data["category"], now, passed_data["item_code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update labor info change
    @app.route('/updatelabor', methods=['PUT'])
    def updatelabor():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE human_items SET description = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, unit_of_measure = %s, category = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
            data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["unit_of_measure"], passed_data["category"], now, passed_data["item_code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    # update equipment info change
    @app.route('/updateequipment', methods=['PUT'])
    def updateequipment():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE physical_equip_items SET description = %s, unit_cost = %s, unit_cost_low = %s, unit_cost_avg = %s, unit_of_measure = %s, category = %s, updated_datetime = %s  WHERE item_code = %s AND org_code = %s"""
            data1 = (passed_data["description"], passed_data["unit_cost_high"], passed_data["unit_cost_low"], passed_data["unit_cost_avg"], passed_data["unit_of_measure"], passed_data["category"], now, passed_data["item_code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update material CU info changes
    @app.route('/updatematerialcuinfo', methods=['PUT'])
    def updatematerialcuinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE physical_compatible_units SET title = %s, description = %s, category = %s, updated_datetime = %s WHERE code = %s AND org_code = %s"""
            data1 = (passed_data["title"], passed_data["description"], passed_data["category"], now, passed_data["cu_code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    # update labor CU info changes
    @app.route('/updatelaborcuinfo', methods=['PUT'])
    def updatelaborcuinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE human_compatible_units SET title = %s, description = %s, category = %s, updated_datetime = %s WHERE code = %s AND org_code = %s"""
            data1 = (passed_data["title"], passed_data["description"], passed_data["category"], now, passed_data["cu_code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update equipment CU info changes
    @app.route('/updateequipmentcuinfo', methods=['PUT'])
    def updateequipmentcuinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE physical_equip_compatible_units SET title = %s, description = %s, category = %s, updated_datetime = %s WHERE code = %s AND org_code = %s"""
            data1 = (passed_data["title"], passed_data["description"], passed_data["category"], now, passed_data["cu_code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update Material CU Category info changes
    @app.route('/updatematerialcucategoryinfo', methods=['PUT'])
    def updatematerialcucategoryinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE physical_cu_categories SET title = %s WHERE category = %s AND org_code = %s"""
            data1 = (passed_data["title"], passed_data["category"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update Labor CU Category info changes
    @app.route('/updatelaborcucategoryinfo', methods=['PUT'])
    def updatelaborcucategoryinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE human_cu_categories SET title = %s WHERE category = %s AND org_code = %s"""
            data1 = (passed_data["title"], passed_data["category"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    # update Equipment CU Category info changes
    @app.route('/updateequipmentcucategoryinfo', methods=['PUT'])
    def updateequipmentcucategoryinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE equip_cu_categories SET title = %s WHERE category = %s AND org_code = %s"""
            data1 = (passed_data["title"], passed_data["category"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update Material Item Category info changes
    @app.route('/updatematerialitemcategoryinfo', methods=['PUT'])
    def updatematerialitemcategoryinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE physical_item_categories SET description = %s WHERE id = %s AND org_code = %s"""
            data1 = (passed_data["description"], passed_data["id"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update Labor Item Category info changes
    @app.route('/updatelaboritemcategoryinfo', methods=['PUT'])
    def updatelaboritemcategoryinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE human_item_categories SET description = %s WHERE id = %s AND org_code = %s"""
            data1 = (passed_data["description"], passed_data["id"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update Equipment Item Category info changes
    @app.route('/updateequipmentitemcategoryinfo', methods=['PUT'])
    def updateequipmentitemcategoryinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE equip_item_categories SET description = %s WHERE id = %s AND org_code = %s"""
            data1 = (passed_data["description"], passed_data["id"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    # update Business Unit info changes
    @app.route('/updatebusinessunitinfo', methods=['PUT'])
    def updatebusinessunitinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE business_units SET description = %s, acronym = %s WHERE code = %s AND org_code = %s"""
            data1 = (passed_data["description"], passed_data["acronym"], passed_data["code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    # update Planner info changes
    @app.route('/updateplannerinfo', methods=['PUT'])
    def updateplannerinfo():
        passed_data = request.get_json()
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            org_code = passed_data.get('org_code')
            
            now = timezone2()  # Ensure this function returns the current datetime
            
            sql1 = """UPDATE planners SET name = %s, email_address = %s WHERE code = %s AND org_code = %s"""
            data1 = (passed_data["name"], passed_data["email_address"], passed_data["code"], org_code)  
            
            cur.execute(sql1, data1)
            
            conn.commit()
            
            # Close the database connection
            cur.close()
            conn.close()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Return success response with 200 status code
            return jsonify({"message": "Updated successfully", "result": "updated"}), 200
        
        except Exception as e:
            # Log the error for debugging purposes (optional)
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
        

    # method to hash password
    def hash_password(password: str) -> str:
        """Hashes the given password and returns the hashed version."""
        if not password:
            raise ValueError("Password cannot be empty")
        
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        return hashed_password

    '''
    def hash_password(password: str) -> bytes:  # Return bytes, not string
        """Hashes the given password and returns the hashed version."""
        if not password:
            raise ValueError("Password cannot be empty")
        
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt())  
        return hashed_password  # Store this in the database as bytes

    def verify_password(login_pw: str, hashed_pw: bytes) -> bool:
        """Checks if the provided login password matches the stored hash."""
        return bcrypt.checkpw(login_pw.encode(), hashed_pw)  # No need to encode hashed_pw
    '''

    #--- Extract and summarize document for work request attachment ----#
    @app.route("/analyze-doc", methods=["GET"])
    def analyze_document():
        filename = request.args.get("filename")
        wrId = request.args.get("wr_id")
        if not filename:
            return jsonify({"error": "filename is required"}), 400
        
        if not wrId:
            return jsonify({"error": "wr_id is required"}), 400
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            extracted_text = extract_text_from_textract(filename)
            summary = summarize_text_with_bedrock(extracted_text)

            sql1 = """UPDATE wr_attachments SET smart_summary = %s WHERE wr_id = %s AND file = %s"""
            data1 = (summary, wrId, filename)
            cur.execute(sql1, data1)

            conn.commit()
            conn.close()

            return jsonify({"summary": summary})
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        #except Exception as e:
        #    logger.error("Error during analysis: %s", str(e))
        #    traceback.print_exc()  # <-- shows full traceback in logs
        #    return jsonify({"error": str(e)}), 500


    #--- Extract and summarize document for work request attachment ----#
    @app.route("/analyze-doc2", methods=["GET"])
    def analyze_document2():
        filename = request.args.get("filename")
        woNumber = request.args.get("wo_number")
        if not filename:
            return jsonify({"error": "filename is required"}), 400
        
        if not woNumber:
            return jsonify({"error": "wo_number is required"}), 400
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            extracted_text = extract_text_from_textract(filename)
            summary = summarize_text_with_bedrock(extracted_text)

            #logger.info("content: ")
            #logger.info(extracted_text)
            #logger.info("summary: ")
            #logger.info(summary)

            sql1 = """UPDATE wo_attachments SET smart_summary = %s WHERE wo_number = %s AND file = %s"""
            data1 = (summary, woNumber, filename)
            cur.execute(sql1, data1)

            conn.commit()
            conn.close()

            return jsonify({"summary": summary})
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        

    #--- generate next work request code ----#
    ###@app.route('/generate_wr_code', methods=['GET'])
    def generate_next_wr_code():
        """
        Generate the next WR code with format: PN-YYYY-XXX.
        - 2nd segment: PH current year (e.g., 2025)
        - 3rd segment: sequential per year (001, 002, ...)
        """
        # Use PH timezone
        current_year = ph_datetime().year
        year_str = str(current_year)
        prefix = f"PN-{year_str}-"

        conn = None
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                SELECT MAX(wr_code) AS last_code
                FROM work_requests
                WHERE wr_code LIKE %s
            """
            like_pattern = prefix + "%"
            cur.execute(sql, (like_pattern,))
            row = cur.fetchone()

            last_code = row["last_code"] if row else None

            if not last_code:
                next_seq = 1
            else:
                try:
                    last_seq_str = last_code.rsplit("-", 1)[-1]
                    last_seq = int(last_seq_str)
                except (ValueError, AttributeError, IndexError):
                    last_seq = 0

                next_seq = last_seq + 1

            next_seq_str = f"{next_seq:03d}"
            new_wr_code = f"{prefix}{next_seq_str}"

            return new_wr_code

        except pymysql.MySQLError as e:
            raise e
        finally:
            if conn:
                conn.close()

    
    #--- generate next work order number ----#
    ###@app.route('/generate_wo_number', methods=['GET'])
    def generate_next_wo_number(wr_code: str) -> str:
        """
        Generate the next WO number based on the given wr_code.

        Pattern:
        WR Reference: PN-2025-001
        WO #:         PN-2025-001-01, PN-2025-001-02, ...

        - Prefix = wr_code (e.g. 'PN-2025-001')
        - 4th segment = 01, 02, ... per wr_code, based on MAX(wo_number).
        """
        prefix = wr_code.strip()        # 'PN-2025-001'
        conn = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                SELECT MAX(wo_code) AS last_wo
                FROM work_orders
                WHERE wo_code LIKE %s
            """
            like_pattern = prefix + "-%"    # 'PN-2025-001-%'
            cur.execute(sql, (like_pattern,))
            row = cur.fetchone()

            last_wo = row["last_wo"] if row else None

            if not last_wo:
                # No WO yet for this WR
                next_seq = 1
            else:
                # Expect format 'PN-2025-001-01'
                try:
                    last_seq_str = last_wo.rsplit("-", 1)[-1]  # '01'
                    last_seq = int(last_seq_str)
                except (ValueError, AttributeError, IndexError):
                    # If bad format, safely reset
                    last_seq = 0

                next_seq = last_seq + 1

            # 4th segment: 2-digit zero padded (01, 02, 03, ...)
            next_seq_str = f"{next_seq:02d}"
            new_wo_number = f"{prefix}-{next_seq_str}"

            return new_wo_number

        except pymysql.MySQLError as e:
            raise e
        finally:
            if conn:
                conn.close()

    # ---------------------------
    # SAVE SERVICE (add/edit)
    # ---------------------------
    @app.route('/saveservice', methods=['POST'])
    def saveservice():
        passed_data = request.get_json()

        required = ["org_code", "description", "instruction", "status", "sequence"]
        for f in required:
            if f not in passed_data:
                return jsonify({"error": f"Missing field: {f}"}), 400

        service_id = passed_data.get("service_id")  # optional for add
        org_code = passed_data["org_code"]
        description = passed_data["description"]
        instruction = passed_data["instruction"]
        status = passed_data["status"]
        sequence = passed_data["sequence"]

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            if service_id is not None and str(service_id) != "":
                sql = """
                    UPDATE services
                    SET description=%s, instruction=%s, status=%s, sequence=%s
                    WHERE service_id=%s AND org_code=%s
                """
                data = (description, instruction, status, sequence, service_id, org_code)
                cur.execute(sql, data)
            else:
                sql = """
                    INSERT INTO services
                        (description, instruction, status, sequence, org_code)
                    VALUES
                        (%s, %s, %s, %s, %s)
                """
                data = (description, instruction, status, sequence, org_code)
                cur.execute(sql, data)
                service_id = cur.lastrowid

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({"result": "success", "service_id": service_id})

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            return jsonify({"error": str(e)}), 500

    
    # ---------------------------
    # SET SERVICE INACTIVE (soft)
    # ---------------------------
    @app.route('/deactivateservice', methods=['POST'])
    def deactivateservice():
        passed_data = request.get_json()

        required = ["org_code", "service_id"]
        for f in required:
            if f not in passed_data:
                return jsonify({"error": f"Missing field: {f}"}), 400

        org_code = passed_data["org_code"]
        service_id = passed_data["service_id"]

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                UPDATE services
                SET status = 0
                WHERE service_id=%s AND org_code=%s
            """
            cur.execute(sql, (service_id, org_code))

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({"result": "success"})

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            return jsonify({"error": str(e)}), 500

    
    # ---------------------------
    # SAVE SERVICE DETAIL (add/edit)
    # ---------------------------
    @app.route('/saveservicedetail', methods=['POST'])
    def saveservicedetail():
        passed_data = request.get_json()

        required = ["org_code", "service_id", "description", "status", "sequence"]
        for f in required:
            if f not in passed_data:
                return jsonify({"error": f"Missing field: {f}"}), 400

        detail_id = passed_data.get("detail_id")  # optional for add
        org_code = passed_data["org_code"]
        service_id = passed_data["service_id"]
        description = passed_data["description"]
        status = passed_data["status"]
        sequence = passed_data["sequence"]

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            if detail_id is not None and str(detail_id) != "":
                sql = """
                    UPDATE service_details
                    SET description=%s, status=%s, sequence=%s
                    WHERE detail_id=%s AND org_code=%s
                """
                cur.execute(sql, (description, status, sequence, detail_id, org_code))
            else:
                sql = """
                    INSERT INTO service_details
                        (service_id, description, status, sequence, org_code)
                    VALUES
                        (%s, %s, %s, %s, %s)
                """
                cur.execute(sql, (service_id, description, status, sequence, org_code))
                detail_id = cur.lastrowid

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({"result": "success", "detail_id": detail_id})

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            return jsonify({"error": str(e)}), 500


    # ---------------------------
    # SET DETAIL INACTIVE (soft)
    # ---------------------------
    @app.route('/deactivateservicedetail', methods=['POST'])
    def deactivateservicedetail():
        passed_data = request.get_json()

        required = ["org_code", "detail_id"]
        for f in required:
            if f not in passed_data:
                return jsonify({"error": f"Missing field: {f}"}), 400

        org_code = passed_data["org_code"]
        detail_id = passed_data["detail_id"]

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                UPDATE service_details
                SET status = 0
                WHERE detail_id=%s AND org_code=%s
            """
            cur.execute(sql, (detail_id, org_code))

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({"result": "success"})

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            return jsonify({"error": str(e)}), 500


    # --- save new project name --- #
    @app.route('/saveprojectname', methods=['POST'])
    def saveprojectname():
        try:
            passed_data = request.get_json(force=True) or {}

            description = (passed_data.get("description") or "").strip()
            org_code = (passed_data.get("org_code") or "").strip()
            user_login = (passed_data.get("user_login") or "").strip()

            # tinyint defaults
            status = passed_data.get("status", 1)
            sequence = passed_data.get("sequence", 0)

            if not org_code:
                return jsonify({"message": "org_code is required"}), 400

            if not description:
                return jsonify({"message": "description is required"}), 400

            # keep within varchar(250)
            if len(description) > 250:
                description = description[:250]

            # normalize ints (safe for tinyint)
            try:
                status = int(status)
            except:
                status = 1

            try:
                sequence = int(sequence)
            except:
                sequence = 0

            conn = dbconnect.getConnection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO project_names
                    (description, status, sequence, org_code)
                VALUES
                    (%s, %s, %s, %s)
            """, (description, status, sequence, org_code))

            conn.commit()

            cursor.close()
            conn.close()

            return jsonify({"message": "inserted"}), 200

        except Exception as e:
            try:
                conn.close()
            except:
                pass
            return jsonify({"message": f"error: {str(e)}"}), 500


    # --- update project name --- #
    @app.route('/updateprojectname', methods=['POST'])
    def updateprojectname():
        conn = None
        cursor = None
        try:
            passed_data = request.get_json(force=True) or {}

            project_id = passed_data.get("project_id", 0)
            description = (passed_data.get("description") or "").strip()
            org_code = (passed_data.get("org_code") or "").strip()
            user_login = (passed_data.get("user_login") or "").strip()

            status = passed_data.get("status", 1)
            sequence = passed_data.get("sequence", 0)

            # validations
            if not org_code:
                return jsonify({"message": "org_code is required"}), 400

            try:
                project_id = int(project_id)
            except:
                project_id = 0

            if project_id <= 0:
                return jsonify({"message": "project_id is required"}), 400

            if not description:
                return jsonify({"message": "description is required"}), 400

            if len(description) > 250:
                description = description[:250]

            try:
                status = int(status)
            except:
                status = 1

            try:
                sequence = int(sequence)
            except:
                sequence = 0

            conn = dbconnect.getConnection()
            cursor = conn.cursor()

            # confirm exists (and belongs to org)
            cursor.execute("""
                SELECT project_id
                FROM project_names
                WHERE project_id = %s AND org_code = %s
                LIMIT 1
            """, (project_id, org_code))
            existing = cursor.fetchone()
            if not existing:
                return jsonify({"message": "not_found"}), 200

            cursor.execute("""
                UPDATE project_names
                SET description = %s,
                    status = %s,
                    sequence = %s
                WHERE project_id = %s
                AND org_code = %s
            """, (description, status, sequence, project_id, org_code))

            conn.commit()

            return jsonify({"message": "updated"}), 200

        except Exception as e:
            return jsonify({"message": f"error: {str(e)}"}), 500

        finally:
            try:
                if cursor:
                    cursor.close()
            except:
                pass
            try:
                if conn:
                    conn.close()
            except:
                pass
    

    @app.route('/savemarkuppercent', methods=['POST'])
    def savemarkuppercent():
        try:
            passed_data = request.get_json() or {}

            org_code = (passed_data.get('org_code') or '').strip()
            mark_up_percent = (passed_data.get('mark_up_percent') or '').strip()

            if not org_code:
                return jsonify({"result": "failed", "message": "org_code required"}), 400

            if not mark_up_percent:
                return jsonify({"result": "failed", "message": "mark_up_percent required"}), 400

            try:
                v = float(mark_up_percent)
            except:
                return jsonify({"result": "failed", "message": "Invalid number"}), 400

            if v < 0 or v > 999.99:
                return jsonify({"result": "failed", "message": "Out of range"}), 400

            conn = dbconnect.getConnection()
            cur = conn.cursor()

            cur.execute("""
                UPDATE sys_references
                SET mark_up_percent = %s
                WHERE org_code = %s
            """, (v, org_code))

            # Insert if not existing
            if cur.rowcount == 0:
                cur.execute("""
                    INSERT INTO references (org_code, mark_up_percent)
                    VALUES (%s, %s)
                """, (org_code, v))

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({"result": "success"}), 200

        except Exception as e:
            return jsonify({"result": "failed", "message": str(e)}), 500

    
    @app.route('/updatewocostestimemarkup', methods=['POST'])
    def updatewocostestimemarkup():
        try:
            passed_data = request.get_json() or {}
            
            #logger.info(passed_data)

            org_code = (passed_data.get('org_code') or '').strip()
            wo_number = passed_data.get('wo_number')

            if not org_code or wo_number is None:
                return jsonify({"result": "failed", "message": "Missing org_code or wo_number"}), 400

            # Safely cast numeric values
            def to_float(val):
                try:
                    return float(val)
                except:
                    return 0.0

            mark_up_percent = to_float(passed_data.get('mark_up_percent'))

            materials_cost = to_float(passed_data.get('materials_cost'))
            materials_cost_low = to_float(passed_data.get('materials_cost_low'))
            materials_cost_avg = to_float(passed_data.get('materials_cost_avg'))

            labor_cost = to_float(passed_data.get('labor_cost'))
            equipment_cost = to_float(passed_data.get('equipment_cost'))
            overhead_cost = to_float(passed_data.get('overhead_cost'))
            contingency_fund = to_float(passed_data.get('contingency_fund'))
            discounts = to_float(passed_data.get('discounts'))

            # Recompute totals from base costs
            total_cost = (
                materials_cost +
                labor_cost +
                equipment_cost +
                overhead_cost +
                contingency_fund
            ) - discounts

            total_cost_low = (
                materials_cost_low +
                labor_cost +
                equipment_cost +
                overhead_cost +
                contingency_fund
            ) - discounts

            total_cost_avg = (
                materials_cost_avg +
                labor_cost +
                equipment_cost +
                overhead_cost +
                contingency_fund
            ) - discounts

            # Compute markup amounts
            mark_up_amount = total_cost * mark_up_percent / 100
            mark_up_amount_low = total_cost_low * mark_up_percent / 100
            mark_up_amount_avg = total_cost_avg * mark_up_percent / 100

            # Compute gross totals
            gross_total_cost = total_cost + mark_up_amount
            gross_total_cost_low = total_cost_low + mark_up_amount_low
            gross_total_cost_avg = total_cost_avg + mark_up_amount_avg

            total_cost = round(total_cost, 2)
            total_cost_low = round(total_cost_low, 2)
            total_cost_avg = round(total_cost_avg, 2)

            mark_up_amount = round(mark_up_amount, 2)
            mark_up_amount_low = round(mark_up_amount_low, 2)
            mark_up_amount_avg = round(mark_up_amount_avg, 2)

            gross_total_cost = round(gross_total_cost, 2)
            gross_total_cost_low = round(gross_total_cost_low, 2)
            gross_total_cost_avg = round(gross_total_cost_avg, 2)

            conn = dbconnect.getConnection()
            cur = conn.cursor()

            cur.execute("""
                UPDATE wo_cost_estimates
                SET
                    materials_cost = %s,
                    materials_cost_low = %s,
                    materials_cost_avg = %s,
                    labor_cost = %s,
                    equipment_cost = %s,
                    overhead_cost = %s,
                    contingency_fund = %s,
                    discounts = %s,
                    total_cost = %s,
                    total_cost_low = %s,
                    total_cost_avg = %s,
                    mark_up_percent = %s,
                    mark_up_amount = %s,
                    mark_up_amount_low = %s,
                    mark_up_amount_avg = %s,
                    gross_total_cost = %s,
                    gross_total_cost_low = %s,
                    gross_total_cost_avg = %s
                WHERE org_code = %s
                AND wo_number = %s
            """, (
                materials_cost,
                materials_cost_low,
                materials_cost_avg,
                labor_cost,
                equipment_cost,
                overhead_cost,
                contingency_fund,
                discounts,
                total_cost,
                total_cost_low,
                total_cost_avg,
                mark_up_percent,
                mark_up_amount,
                mark_up_amount_low,
                mark_up_amount_avg,
                gross_total_cost,
                gross_total_cost_low,
                gross_total_cost_avg,
                org_code,
                wo_number
            ))

            conn.commit()

            return jsonify({"result": "success"}), 200

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            return jsonify({"result": "failed", "message": str(e)}), 500

        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass

    
    #--- save work order revenue entries ----#
    @app.route('/saveworevenueentries', methods=['POST'])
    def saveworevenueentries():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            wo_number = passed_data["wo_number"]
            org_code = passed_data["org_code"]
            service_id = passed_data.get("service_id")
            entries = passed_data.get("entries", [])

            # Get old revenue ids
            sql_old = """
                SELECT revenue_id
                FROM wo_revenues
                WHERE wo_number = %s
                AND org_code = %s
            """
            cur.execute(sql_old, (wo_number, org_code))
            old_rows = cur.fetchall()

            old_ids = []
            for r in old_rows:
                if isinstance(r, dict):
                    old_ids.append(r.get("revenue_id"))
                else:
                    old_ids.append(r[0])

            # Delete child attachments first
            if old_ids:
                placeholders = ','.join(['%s'] * len(old_ids))
                sql_del_att = f"""
                    DELETE FROM revenue_attachments
                    WHERE revenue_id IN ({placeholders})
                    AND org_code = %s
                """
                cur.execute(sql_del_att, tuple(old_ids) + (org_code,))

            # Delete old revenue rows
            sql_del_rev = """
                DELETE FROM wo_revenues
                WHERE wo_number = %s
                AND org_code = %s
            """
            cur.execute(sql_del_rev, (wo_number, org_code))

            # Insert fresh rows
            for item in entries:
                revenue_code = item.get('revenue_code')
                amount = item.get('amount', 0)
                attachments = item.get('attachments', []) or []

                if not revenue_code:
                    continue

                sql_rev = """
                    INSERT INTO wo_revenues
                    (
                        wo_number,
                        revenue_code,
                        amount,
                        created_datetime,
                        org_code,
                        service_id
                    )
                    VALUES (%s, %s, %s, NOW(), %s, %s)
                """
                data_rev = (
                    wo_number,
                    revenue_code,
                    amount,
                    org_code,
                    service_id,
                )
                cur.execute(sql_rev, data_rev)
                revenue_id = cur.lastrowid

                for att in attachments:
                    file_url = att.get('file_url')
                    if not file_url:
                        continue

                    sql_att = """
                        INSERT INTO revenue_attachments
                        (
                            revenue_id,
                            file,
                            org_code
                        )
                        VALUES (%s, %s, %s)
                    """
                    data_att = (
                        revenue_id,
                        file_url,
                        org_code,
                    )
                    cur.execute(sql_att, data_att)

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                "message": "Revenue entries saved successfully",
                "result": "Success"
            }), 201

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass

            return jsonify({
                "message": str(e),
                "result": None
            }), 500
    

    #--- save work order cost of services entries ----#
    @app.route('/savewoservicecostentries', methods=['POST'])
    def savewoservicecostentries():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            now = timezone2()
            wo_number = passed_data["wo_number"]

            # --- get org_code from work_orders ---
            sql1 = """SELECT org_code FROM work_orders WHERE wo_number = %s"""
            cur.execute(sql1, (wo_number,))
            result = cur.fetchall()

            if not result:
                return jsonify({"error": "Work order not found"}), 404

            if isinstance(result[0], dict):
                org_code = result[0]["org_code"]
            else:
                org_code = result[0][0]

            # --- get old cost_service_ids first ---
            sql_old = """
                SELECT cost_service_id
                FROM wo_cost_services
                WHERE wo_number = %s
                AND org_code = %s
            """
            cur.execute(sql_old, (wo_number, org_code))
            old_rows = cur.fetchall()

            old_ids = []
            for r in old_rows:
                if isinstance(r, dict):
                    old_ids.append(r.get("cost_service_id"))
                else:
                    old_ids.append(r[0])

            # --- delete child attachments first ---
            if old_ids:
                placeholders = ','.join(['%s'] * len(old_ids))
                sql_del_att = f"""
                    DELETE FROM cost_service_attachments
                    WHERE cost_service_id IN ({placeholders})
                    AND org_code = %s
                """
                cur.execute(sql_del_att, tuple(old_ids) + (org_code,))

            # --- delete existing cost rows ---
            sql_del = """
                DELETE FROM wo_cost_services
                WHERE wo_number = %s
                AND org_code = %s
            """
            cur.execute(sql_del, (wo_number, org_code))

            # --- insert fresh cost rows + attachments ---
            sql_insert = """
                INSERT INTO wo_cost_services
                (wo_number, service_code, amount, created_datetime, org_code)
                VALUES (%s, %s, %s, %s, %s)
            """

            for entry in passed_data.get("service_entries", []):
                service_code = entry.get("service_code")
                amount = entry.get("amount", 0)
                attachments = entry.get("attachments", []) or []

                if not service_code:
                    continue

                cur.execute(sql_insert, (wo_number, service_code, amount, now, org_code))
                cost_service_id = cur.lastrowid

                for att in attachments:
                    file_url = att.get("file_url")
                    if not file_url:
                        continue

                    sql_att = """
                        INSERT INTO cost_service_attachments
                        (cost_service_id, file, org_code)
                        VALUES (%s, %s, %s)
                    """
                    cur.execute(sql_att, (cost_service_id, file_url, org_code))

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({
                "message": "Cost of services entries saved successfully",
                "result": "Success"
            }), 201

        except Exception as e:
            try:
                conn.rollback()
            except:
                pass

            return jsonify({
                "message": str(e),
                "result": None
            }), 500
                

    # ── Revenue Chart of Accounts ─────────────────────────────────────────────

    #--- save new revenue account code ----#
    '''
    @app.route('/postnewrevenueaccount', methods=['POST'])
    def postnewrevenueaccount():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            code          = (passed_data.get('code') or '').strip()
            account_title = (passed_data.get('account_title') or '').strip()
            org_code      = (passed_data.get('org_code') or '').strip()

            # ── basic validation ────────────────────────────────────────────
            if not code:
                return jsonify({"error": "code is required"}), 400
            if not account_title:
                return jsonify({"error": "account_title is required"}), 400
            if not org_code:
                return jsonify({"error": "org_code is required"}), 400

            # ── duplicate check ─────────────────────────────────────────────
            cur.execute(
                "SELECT code FROM revenue_account_codes "
                "WHERE code = %s AND org_code = %s",
                (code, org_code)
            )
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({"error": f'Account code "{code}" already exists.'}), 409

            # ── insert ──────────────────────────────────────────────────────
            sql = """
                INSERT INTO revenue_account_codes
                    (code, account_title, status, org_code)
                VALUES
                    (%s, %s, 1, %s)
            """
            cur.execute(sql, (code, account_title, org_code))

            conn.commit()

            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            return jsonify({"message": "New Revenue Account created successfully", "result": "inserted"}), 201

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    '''
    @app.route('/postnewrevenueaccount', methods=['POST'])
    def postnewrevenueaccount():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            code = (passed_data.get('code') or '').strip()
            account_title = (passed_data.get('account_title') or '').strip()
            org_code = (passed_data.get('org_code') or '').strip()

            service_id = passed_data.get('service_id')
            try:
                service_id = int(service_id) if service_id not in (None, '') else None
            except (TypeError, ValueError):
                service_id = None

            if not code:
                return jsonify({"error": "code is required"}), 400

            if not account_title:
                return jsonify({"error": "account_title is required"}), 400

            if not org_code:
                return jsonify({"error": "org_code is required"}), 400

            if service_id is not None:
                cur.execute(
                    """
                    SELECT service_id
                    FROM services
                    WHERE service_id = %s
                    AND org_code = %s
                    AND status = 1
                    """,
                    (service_id, org_code)
                )

                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({"error": "Invalid Scope selected."}), 400

            cur.execute(
                """
                SELECT code
                FROM revenue_account_codes
                WHERE code = %s
                AND org_code = %s
                """,
                (code, org_code)
            )

            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({
                    "error": f'Account code "{code}" already exists.'
                }), 409

            sql = """
                INSERT INTO revenue_account_codes
                    (code, account_title, status, org_code, service_id)
                VALUES
                    (%s, %s, 1, %s, %s)
            """

            cur.execute(sql, (code, account_title, org_code, service_id))
            conn.commit()

            cur.close()
            conn.close()

            return jsonify({
                "message": "New Revenue Account created successfully",
                "result": "inserted"
            }), 201

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500

    #--- update revenue account code ----#
    '''
    @app.route('/updaterevenueaccount', methods=['PUT'])
    def updaterevenueaccount():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            code          = (passed_data.get('code') or '').strip()
            account_title = (passed_data.get('account_title') or '').strip()
            org_code      = (passed_data.get('org_code') or '').strip()

            try:
                status = int(passed_data.get('status', 1))
            except (TypeError, ValueError):
                status = 1

            # ── basic validation ────────────────────────────────────────────
            if not code:
                return jsonify({"error": "code is required"}), 400
            if not account_title:
                return jsonify({"error": "account_title is required"}), 400
            if status not in (0, 1):
                return jsonify({"error": "status must be 0 or 1"}), 400

            # ── update ──────────────────────────────────────────────────────
            sql = """
                UPDATE revenue_account_codes
                   SET account_title = %s,
                       status        = %s
                 WHERE code     = %s
                   AND org_code = %s
            """
            cur.execute(sql, (account_title, status, code, org_code))

            conn.commit()

            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            return jsonify({"message": "Revenue Account updated successfully", "result": "updated"}), 200

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500
    '''
    @app.route('/updaterevenueaccount', methods=['PUT'])
    def updaterevenueaccount():
        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            code = (passed_data.get('code') or '').strip()
            account_title = (passed_data.get('account_title') or '').strip()
            org_code = (passed_data.get('org_code') or '').strip()

            try:
                status = int(passed_data.get('status', 1))
            except (TypeError, ValueError):
                status = 1

            service_id = passed_data.get('service_id')
            try:
                service_id = int(service_id) if service_id not in (None, '') else None
            except (TypeError, ValueError):
                service_id = None

            if not code:
                return jsonify({"error": "code is required"}), 400

            if not account_title:
                return jsonify({"error": "account_title is required"}), 400

            if not org_code:
                return jsonify({"error": "org_code is required"}), 400

            if status not in (0, 1):
                return jsonify({"error": "status must be 0 or 1"}), 400

            if service_id is not None:
                cur.execute(
                    """
                    SELECT service_id
                    FROM services
                    WHERE service_id = %s
                    AND org_code = %s
                    AND status = 1
                    """,
                    (service_id, org_code)
                )

                if not cur.fetchone():
                    cur.close()
                    conn.close()
                    return jsonify({"error": "Invalid Scope selected."}), 400

            sql = """
                UPDATE revenue_account_codes
                SET account_title = %s,
                    status = %s,
                    service_id = %s
                WHERE code = %s
                AND org_code = %s
            """

            cur.execute(sql, (account_title, status, service_id, code, org_code))
            conn.commit()

            cur.close()
            conn.close()

            return jsonify({
                "message": "Revenue Account updated successfully",
                "result": "updated"
            }), 200

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500

    # ── Service Chart of Accounts ─────────────────────────────────────────────

    #--- save new service account code ----#
    @app.route('/postnewserviceaccount', methods=['POST'])
    def postnewserviceaccount():

        VALID_WAC_CATEGORIES = {
            'Materials', 'Labor', 'Equipment',
            'Overhead', 'Contingency', 'Discounts'
        }

        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            code          = (passed_data.get('code') or '').strip()
            account_title = (passed_data.get('account_title') or '').strip()
            wac_category  = (passed_data.get('wac_category') or '').strip()
            org_code      = (passed_data.get('org_code') or '').strip()

            # ── basic validation ────────────────────────────────────────────
            if not code:
                return jsonify({"error": "code is required"}), 400
            if not account_title:
                return jsonify({"error": "account_title is required"}), 400
            if wac_category not in VALID_WAC_CATEGORIES:
                return jsonify({"error": f"wac_category must be one of: {', '.join(sorted(VALID_WAC_CATEGORIES))}"}), 400
            if not org_code:
                return jsonify({"error": "org_code is required"}), 400

            # ── duplicate check ─────────────────────────────────────────────
            cur.execute(
                "SELECT code FROM service_account_codes "
                "WHERE code = %s AND org_code = %s",
                (code, org_code)
            )
            if cur.fetchone():
                cur.close()
                conn.close()
                return jsonify({"error": f'Account code "{code}" already exists.'}), 409

            # ── insert ──────────────────────────────────────────────────────
            sql = """
                INSERT INTO service_account_codes
                    (code, account_title, status, org_code, wac_category)
                VALUES
                    (%s, %s, 1, %s, %s)
            """
            cur.execute(sql, (code, account_title, org_code, wac_category))

            conn.commit()

            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            return jsonify({"message": "New Service Account created successfully", "result": "inserted"}), 201

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500


    #--- update service account code ----#
    @app.route('/updateserviceaccount', methods=['PUT'])
    def updateserviceaccount():

        VALID_WAC_CATEGORIES = {
            'Materials', 'Labor', 'Equipment',
            'Overhead', 'Contingency', 'Discounts'
        }

        passed_data = request.get_json()

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            code          = (passed_data.get('code') or '').strip()
            account_title = (passed_data.get('account_title') or '').strip()
            wac_category  = (passed_data.get('wac_category') or '').strip()
            org_code      = (passed_data.get('org_code') or '').strip()

            try:
                status = int(passed_data.get('status', 1))
            except (TypeError, ValueError):
                status = 1

            # ── basic validation ────────────────────────────────────────────
            if not code:
                return jsonify({"error": "code is required"}), 400
            if not account_title:
                return jsonify({"error": "account_title is required"}), 400
            if wac_category not in VALID_WAC_CATEGORIES:
                return jsonify({"error": f"wac_category must be one of: {', '.join(sorted(VALID_WAC_CATEGORIES))}"}), 400
            if status not in (0, 1):
                return jsonify({"error": "status must be 0 or 1"}), 400

            # ── update ──────────────────────────────────────────────────────
            sql = """
                UPDATE service_account_codes
                   SET account_title = %s,
                       wac_category  = %s,
                       status        = %s
                 WHERE code     = %s
                   AND org_code = %s
            """
            cur.execute(sql, (account_title, wac_category, status, code, org_code))

            conn.commit()

            cur.close()
            conn.close()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            return jsonify({"message": "Service Account updated successfully", "result": "updated"}), 200

        except Exception as e:
            print(str(e))
            return jsonify({"error": "Internal server error"}), 500

    
    #--- save proposal details for work order (for 2-proposal template) ----#
    @app.route('/savewoproposaldetails', methods=['POST'])
    def savewoproposaldetails():

        data = request.get_json() or {}

        wo_number = data.get('wo_number')
        org_code = data.get('org_code')

        if not wo_number:
            return jsonify({"error": "1", "message": "No wo_number field provided."}), 400

        if not org_code:
            return jsonify({"error": "1", "message": "No org_code field provided."}), 400

        conn = None
        cur = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """
                INSERT INTO wo_proposal_details (
                    wo_number,
                    org_code,
                    recipient_name,
                    recipient_role,
                    recipient_company,
                    scope_of_work,
                    timeline,
                    terms_conditions,
                    title_after_terms,
                    payment_terms,
                    validity_days,
                    customer_name,
                    created_by,
                    updated_by
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    recipient_name = VALUES(recipient_name),
                    recipient_role = VALUES(recipient_role),
                    recipient_company = VALUES(recipient_company),
                    scope_of_work = VALUES(scope_of_work),
                    timeline = VALUES(timeline),
                    terms_conditions = VALUES(terms_conditions),
                    title_after_terms = VALUES(title_after_terms),
                    payment_terms = VALUES(payment_terms),
                    validity_days = VALUES(validity_days),
                    customer_name = VALUES(customer_name),
                    updated_by = VALUES(updated_by),
                    updated_datetime = CURRENT_TIMESTAMP
            """

            user_login = data.get('updated_by') or data.get('created_by') or ''

            values = (
                wo_number,
                org_code,
                data.get('recipient_name', ''),
                data.get('recipient_role', ''),
                data.get('recipient_company', ''),
                data.get('scope_of_work', ''),
                data.get('timeline', ''),
                data.get('terms_conditions', ''),
                data.get('title_after_terms', ''),
                data.get('payment_terms', ''),
                data.get('validity_days', ''),
                data.get('customer_name', ''),
                user_login,
                user_login,
            )

            cur.execute(sql, values)
            conn.commit()

            return jsonify({
                "error": "0",
                "message": "Proposal details saved successfully"
            }), 200

        except Exception as e:
            if conn:
                conn.rollback()

            return jsonify({
                "error": "1",
                "message": "Failed to save proposal details",
                "details": str(e)
            }), 500

        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except:
                pass

'''
    #--- OCR callback for WR attachment ----#
    @app.route('/post_wr_attachment_ocr_raw_text', methods=['POST'])
    def post_wr_attachment_ocr_raw_text():

        data = request.get_json() or {}

        attachment_id = data.get('source_record_id')
        status = data.get('status')
        raw_text = data.get('raw_text')
        error_message = data.get('error_message')
        job_id = data.get('job_id')

        internal_token = request.headers.get('X-Internal-Token')

        if internal_token != os.getenv("INTERNAL_API_TOKEN"):
            return jsonify({
                "error": "1",
                "message": "Unauthorized"
            }), 401

        if not attachment_id:
            return jsonify({
                "error": "1",
                "message": "No source_record_id provided."
            }), 400

        conn = None
        cur = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            if status == "completed":

                sql = """
                    UPDATE wr_attachments
                    SET
                        raw_text = %s
                    WHERE id = %s
                """

                cur.execute(sql, (
                    raw_text,
                    attachment_id
                ))

            elif status == "failed":

                sql = """
                    UPDATE wr_attachments
                    SET
                        raw_text = %s
                    WHERE id = %s
                """

                cur.execute(sql, (
                    f"OCR FAILED: {error_message}",
                    attachment_id
                ))

            conn.commit()

            return jsonify({
                "error": "0",
                "message": "WR attachment OCR updated successfully",
                "job_id": job_id
            }), 200

        except Exception as e:

            if conn:
                conn.rollback()

            return jsonify({
                "error": "1",
                "message": "Failed to update WR attachment OCR",
                "details": str(e)
            }), 500

        finally:
            try:
                if cur:
                    cur.close()

                if conn:
                    conn.close()

            except:
                pass


    #--- OCR callback for WO attachment ----#
    @app.route('/post_wo_attachment_ocr_raw_text', methods=['POST'])
    def post_wo_attachment_ocr_raw_text():

        data = request.get_json() or {}

        attachment_id = data.get('source_record_id')
        status = data.get('status')
        raw_text = data.get('raw_text')
        error_message = data.get('error_message')
        job_id = data.get('job_id')

        internal_token = request.headers.get('X-Internal-Token')

        if internal_token != os.getenv("INTERNAL_API_TOKEN"):
            return jsonify({
                "error": "1",
                "message": "Unauthorized"
            }), 401

        if not attachment_id:
            return jsonify({
                "error": "1",
                "message": "No source_record_id provided."
            }), 400

        conn = None
        cur = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            if status == "completed":

                sql = """
                    UPDATE wo_attachments
                    SET
                        raw_text = %s
                    WHERE id = %s
                """

                cur.execute(sql, (
                    raw_text,
                    attachment_id
                ))

            elif status == "failed":

                sql = """
                    UPDATE wo_attachments
                    SET
                        raw_text = %s
                    WHERE id = %s
                """

                cur.execute(sql, (
                    f"OCR FAILED: {error_message}",
                    attachment_id
                ))

            conn.commit()

            return jsonify({
                "error": "0",
                "message": "WO attachment OCR updated successfully",
                "job_id": job_id
            }), 200

        except Exception as e:

            if conn:
                conn.rollback()

            return jsonify({
                "error": "1",
                "message": "Failed to update WO attachment OCR",
                "details": str(e)
            }), 500

        finally:
            try:
                if cur:
                    cur.close()

                if conn:
                    conn.close()

            except:
                pass
'''