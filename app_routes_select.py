import bcrypt
from flask import request, jsonify
import dbconnect
import pymysql, pymysql.cursors
#import simplejson as json
from datetime import datetime, timedelta
import json
import pymysql.cursors
import pytz

# for google FCM
import google.auth.transport.requests

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
    
def ph_datetime():
    try:
        tz = pytz.timezone('UTC')
        now = datetime.now(tz) + timedelta(hours=8)  # PH timezone
        return now
    except Exception as e:
        raise e

def register_select_routes(app):
    #--- authenticate user login ----#
    @app.route('/userauth', methods=['GET'])
    def userauth():
        if 'user_email' in request.args:
            user_email = request.args['user_email']
        else:
            return "Error: No Email Address field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT auth_channel, password, member_id FROM users WHERE email_address = %s"""
            data1 = (user_email) 
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are users
            if result:
                return jsonify({
                    "message": "Users retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No users found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve users",
                "error": str(e)
            }), 500
    

    #--- authenticate user google login ----#
    @app.route('/usergoogleauth', methods=['GET'])
    def usergoogleauth():
        if 'user_email' in request.args:
            user_email = request.args['user_email']
        else:
            return "Error: No Email Address field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT auth_channel, member_id FROM users WHERE email_address = %s"""
            data1 = (user_email) 
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are users
            if result:
                return jsonify({
                    "message": "Users retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No users found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve users",
                "error": str(e)
            }), 500
            

    #--- get user's information ----#
    @app.route('/getuserinfo', methods=['GET'])
    def getuserinfo():
        if 'user_email' in request.args:
            user_email = request.args['user_email']
        else:
            return "Error: No User Email field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.user_id AS user_id, a.email_address AS email_address, a.profile_photo AS profile_photo, a.personnel_id AS personnel_id, a.active AS active, a.device_id AS device_id, CONCAT(b.firstname,' ',b.middlename,' ',b.lastname) AS fullname FROM users a LEFT JOIN personnel b ON a.personnel_id = b.personnel_id WHERE a.email_address = %s"""
            data1 = (user_email)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are users
            if result:
                return jsonify({
                    "message": "Users retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No users found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve users",
                "error": str(e)
            }), 500


    #--- get all users ----#
    '''
    @app.route('/getuserslist', methods=['GET'])
    def getuserslist():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM app_users WHERE org_code = %s"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are users
            if result:
                return jsonify({
                    "message": "Users retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No users found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve users",
                "error": str(e)
            }), 500
    '''
    #--- get all users ----#
    @app.route('/getuserslist', methods=['GET'])
    def getuserslist():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return jsonify({
                "message": "No Organization Code field provided.",
                "result": []
            }), 400

        conn = None
        cur = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql1 = """
                SELECT
                    id,
                    `user`,
                    built_in,
                    oauth,
                    status,
                    firstname,
                    lastname,
                    org_code,
                    position_title,
                    CASE
                        WHEN signature_file IS NOT NULL THEN 1
                        ELSE 0
                    END AS has_signature
                FROM app_users
                WHERE org_code = %s
                ORDER BY `user` ASC
            """

            cur.execute(sql1, (org_code,))
            result = cur.fetchall()

            return jsonify({
                "message": "Users retrieved successfully",
                "result": result or []
            }), 200

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve users",
                "error": str(e),
                "result": []
            }), 500

        finally:
            try:
                if cur:
                    cur.close()
                if conn:
                    conn.close()
            except:
                pass


    #--- get all roles ----#
    @app.route('/getroleslist', methods=['GET'])
    def getroleslist():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM app_roles WHERE org_code = %s"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are users
            if result:
                return jsonify({
                    "message": "Roles retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No roles found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve roles",
                "error": str(e)
            }), 500


    #--- get all roles per user ----#
    @app.route('/getuserroleslist', methods=['GET'])
    def getuserroleslist():
        if 'user_name' in request.args:
            user_name = request.args['user_name']
        else:
            return "Error: No User Name field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM app_user_roles WHERE user = %s AND org_code = %s"""
            data1 = (user_name, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are users
            if result:
                return jsonify({
                    "message": "Roles retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No roles found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve roles",
                "error": str(e)
            }), 500
        
    
    #--- get IDs for ASANA ----#
    @app.route('/getasanaids', methods=['GET'])
    def getasanaids():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT COALESCE(pat, 'none') AS pat, COALESCE(workspace_gid, 'none') AS workspace_gid, COALESCE(portfolio_gid, 'none') AS portfolio_gid, COALESCE(team_gid, 'none') AS team_gid FROM asana_ids WHERE org_code = %s"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchone()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Asana IDs retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Asana IDs found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve customer types",
                "error": str(e)
            }), 500
        
        
    #--- get all work requests v2 (with pagination and filters + My Requests perfect paging) ----#
    @app.route('/getworkrequests', methods=['GET'])
    def getworkrequests():
        if 'email' in request.args:
            email = request.args['email']
        else:
            return "Error: No Email Address field provided. Please specify it."

        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        # ✅ NEW: My Requests toggle (default ON)
        my_only = request.args.get('my_only', '1').strip()  # 1 = My Requests, 0 = All

        # ✅ NEW: pagination (defaults)
        try:
            offset = int(request.args.get('offset', 0))
        except:
            offset = 0

        try:
            limit = int(request.args.get('limit', 12))
        except:
            limit = 12

        if offset < 0:
            offset = 0
        if limit <= 0:
            limit = 12

        # ✅ NEW: optional server-side filters
        business_unit = request.args.get('business_unit', '').strip()  # BU code
        status_filter = request.args.get('status', '').strip()         # WR status text
        q = request.args.get('q', '').strip()                          # project_desc search
        service_id_raw = request.args.get('service_id', '').strip()    # scope/service id

        service_id = None
        if service_id_raw != "":
            try:
                service_id = int(service_id_raw)
            except:
                service_id = None

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            # ✅ NEW: total count (avoid inflated totals; use EXISTS for service filter)
            # Keep your original branching behavior, but add My Requests logic for perfect paging.
            if email != "":
                sql_count = """
                    SELECT COUNT(DISTINCT a.wr_id) AS total
                    FROM work_requests a
                    WHERE a.org_code = %s
                """
                data_count = [org_code]
            else:
                sql_count = """
                    SELECT COUNT(DISTINCT a.wr_id) AS total
                    FROM work_requests a
                    WHERE a.org_code = %s
                """
                data_count = [org_code]

            # ✅ My Requests filter (COUNT – paging safe)
            # My Requests = created by me OR I am planner
            if my_only == "1" and email != "":
                sql_count += """
                    AND (
                        a.email_address = %s
                        OR EXISTS (
                            SELECT 1
                            FROM work_order_team wt
                            WHERE wt.wr_id = a.wr_id
                            AND wt.role = 'planner'
                            AND wt.user = %s
                        )
                    )
                """
                data_count.extend([email, email])

            # ✅ keep your other server-side filters
            if business_unit != "":
                sql_count += " AND a.business_unit = %s"
                data_count.append(business_unit)

            if status_filter != "":
                sql_count += " AND a.status = %s"
                data_count.append(status_filter)

            if q != "":
                sql_count += " AND a.project_desc LIKE %s"
                data_count.append(f"%{q}%")

            if service_id is not None:
                sql_count += """
                    AND EXISTS (
                        SELECT 1
                        FROM requested_services rsx
                        WHERE rsx.wr_id = a.wr_id
                        AND rsx.org_code = a.org_code
                        AND rsx.service_id = %s
                    )
                """
                data_count.append(service_id)

            cur.execute(sql_count, tuple(data_count))
            total_row = cur.fetchone()
            total = int(total_row["total"]) if total_row and "total" in total_row else 0

            # -----------------------------
            # ORIGINAL LOGIC FLOW PRESERVED
            # (email != "" branch, else branch)
            # -----------------------------
            if email != "":
                sql1 = """
                    SELECT 
                        a.wr_id AS wr_id,
                        a.wr_code AS wr_code, 
                        a.firstname AS firstname,
                        a.middlename AS middlename,
                        a.lastname AS lastname,
                        a.email_address AS email_address,
                        wotp.planner AS planner,
                        a.business_unit AS business_unit, 
                        e.description AS business_unit_desc, 
                        e.acronym AS business_unit_acronym,
                        a.customer_type AS customer_type_code,
                        b.description AS customer_type, 
                        a.project_location AS project_location,
                        DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        a.project_desc AS project_desc,
                        a.project_details AS project_details,
                        a.submitted_datetime AS submitted_datetime,
                        a.status AS status, 
                        a.org_code AS org_code, 
                        a.project_gid AS project_gid,
                        a.priority_level AS priority_level,
                        wpl.description AS priority_level_desc,
                        rs.service_id AS service_id,
                        s.description AS scope,
                        COUNT(DISTINCT d.id) AS unread_count,
                        COALESCE(woc.open_work_order_count, 0) AS open_work_order_count
                    FROM 
                        work_requests a
                    LEFT JOIN 
                        customer_types b ON a.customer_type = b.code
                    LEFT JOIN
                        business_units e ON a.business_unit = e.code 
                    LEFT JOIN 
                        app_chatbox d 
                            ON a.project_gid = d.project_gid 
                            AND d.read_datetime IS NULL
                    LEFT JOIN
                        requested_services rs
                            ON rs.wr_id = a.wr_id
                            AND rs.org_code = a.org_code
                    LEFT JOIN
                        services s
                            ON s.service_id = rs.service_id 
                    LEFT JOIN (
                            SELECT 
                                wr_id,
                                MAX(user) AS planner
                            FROM work_order_team
                            WHERE role = 'planner'
                            GROUP BY wr_id
                        ) wotp
                            ON wotp.wr_id = a.wr_id 
                    LEFT JOIN 
                        wr_priority_levels wpl
                            ON a.priority_level = wpl.code 
                    LEFT JOIN (
                        SELECT 
                            wr_id,
                            COUNT(*) AS open_work_order_count
                        FROM work_orders
                        WHERE status NOT IN ('Completed', 'Cancelled')
                        GROUP BY wr_id
                    ) woc
                        ON woc.wr_id = a.wr_id 
                    WHERE 
                        a.org_code = %s
                """
                params = [org_code]
            else:
                sql1 = """
                    SELECT 
                        a.wr_id AS wr_id,
                        a.wr_code AS wr_code, 
                        a.firstname AS firstname,
                        a.middlename AS middlename,
                        a.lastname AS lastname,
                        a.email_address AS email_address,
                        wotp.planner AS planner,
                        a.business_unit AS business_unit, 
                        e.description AS business_unit_desc, 
                        e.acronym AS business_unit_acronym, 
                        a.customer_type AS customer_type_code,
                        b.description AS customer_type, 
                        a.project_location AS project_location,
                        DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        a.project_desc AS project_desc,
                        a.project_details AS project_details,
                        a.submitted_datetime AS submitted_datetime,
                        a.status AS status, 
                        a.org_code AS org_code, 
                        a.project_gid AS project_gid, 
                        a.priority_level AS priority_level,
                        wpl.description AS priority_level_desc,
                        rs.service_id AS service_id,
                        s.description AS scope,
                        COUNT(DISTINCT d.id) AS unread_count,
                        COALESCE(woc.open_work_order_count, 0) AS open_work_order_count
                    FROM 
                        work_requests a
                    LEFT JOIN 
                        customer_types b ON a.customer_type = b.code
                    LEFT JOIN
                        business_units e ON a.business_unit = e.code 
                    LEFT JOIN 
                        app_chatbox d 
                            ON a.project_gid = d.project_gid 
                            AND d.read_datetime IS NULL
                    LEFT JOIN
                        requested_services rs
                            ON rs.wr_id = a.wr_id
                            AND rs.org_code = a.org_code
                    LEFT JOIN
                        services s
                            ON s.service_id = rs.service_id 
                    LEFT JOIN (
                            SELECT 
                                wr_id,
                                MAX(user) AS planner
                            FROM work_order_team
                            WHERE role = 'planner'
                            GROUP BY wr_id
                        ) wotp
                            ON wotp.wr_id = a.wr_id 
                    LEFT JOIN 
                        wr_priority_levels wpl
                            ON a.priority_level = wpl.code 
                    LEFT JOIN (
                        SELECT 
                            wr_id,
                            COUNT(*) AS open_work_order_count
                        FROM work_orders
                        WHERE status NOT IN ('Completed', 'Cancelled')
                        GROUP BY wr_id
                    ) woc
                        ON woc.wr_id = a.wr_id 
                    WHERE 
                        a.org_code = %s
                """
                params = [org_code]

            # ✅ NEW: My Requests filter (DATA query) — paging safe
            if my_only == "1" and email != "":
                sql1 += """
                    AND (
                        a.email_address = %s
                        OR wotp.planner = %s
                    )
                """
                params.extend([email, email])

            # ✅ NEW: server-side filters (same list for both branches)
            if business_unit != "":
                sql1 += " AND a.business_unit = %s"
                params.append(business_unit)

            if status_filter != "":
                sql1 += " AND a.status = %s"
                params.append(status_filter)

            if q != "":
                sql1 += " AND a.project_desc LIKE %s"
                params.append(f"%{q}%")

            if service_id is not None:
                sql1 += " AND rs.service_id = %s"
                params.append(service_id)

            # ✅ keep your GROUP BY and ORDER BY; add LIMIT/OFFSET
            sql1 += """
                GROUP BY 
                    a.wr_id, a.firstname, a.middlename, a.lastname, a.email_address, 
                    a.business_unit, e.description,
                    a.customer_type, b.description, 
                    a.project_location, a.proposal_deadline, a.job_start_date, a.job_end_date, 
                    a.project_desc, a.project_details, a.submitted_datetime, a.status, 
                    a.org_code, a.project_gid, wotp.planner,
                    woc.open_work_order_count 
                ORDER BY 
                    a.submitted_datetime DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

            cur.execute(sql1, tuple(params))
            result = cur.fetchall()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            if result:
                return jsonify({
                    "message": "Work Requests retrieved successfully",
                    "total": total,
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work requests found",
                    "total": total,
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work requests",
                "error": str(e)
            }), 500


    #--- get work requests per WR Id ----#
    @app.route('/getworkrequest', methods=['GET'])
    def getworkrequest():
        if 'wr_id' in request.args:
            wr_id = request.args['wr_id']
        else:
            return "Error: No WR Id field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """
                    SELECT 
                        a.wr_id AS wr_id,
                        a.firstname AS firstname,
                        a.middlename AS middlename,
                        a.lastname AS lastname,
                        a.email_address AS email_address,
                        a.business_unit AS business_unit, 
                        b.description AS customer_type,
                        a.project_location AS project_location,
                        DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        a.project_desc AS project_desc,
                        a.project_details AS project_details,
                        a.submitted_datetime AS submitted_datetime,
                        a.status AS status, 
                        a.org_code AS org_code 
                    FROM 
                        work_requests a
                    LEFT JOIN 
                        customer_types b ON a.customer_type = b.code
                    LEFT JOIN 
                        wr_pm_data c ON a.wr_id = c.wr_id
                    WHERE 
                        a.wr_id = %s 
                        AND a.org_code = %s 
                """
            data1 = (wr_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are work requests
            if result:
                return jsonify({
                    "message": "Work Request retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work request found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work request",
                "error": str(e)
            }), 500


    #--- get all customers ----#
    @app.route('/getcustomers', methods=['GET'])
    def getcustomers():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT id, CONCAT(firstname, ' ', middlename, ' ', lastname) AS fullname, firstname, middlename, lastname, email_address, contact_number, street_address, city, province, company_name, org_code FROM customers WHERE org_code = %s ORDER BY fullname"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are work requests
            if result:
                return jsonify({
                    "message": "Customers retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No customers found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve customers",
                "error": str(e)
            }), 500


    #--- get all suppliers ----#
    @app.route('/getsuppliers', methods=['GET'])
    def getsuppliers():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM suppliers WHERE org_code = %s ORDER BY name"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are work requests
            if result:
                return jsonify({
                    "message": "Suppliers retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No suppliers found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve suppliers",
                "error": str(e)
            }), 500
            

    #--- get all customer types ----#
    @app.route('/getcustomertypes', methods=['GET'])
    def getcustomertypes():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM customer_types WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Customer Types retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No customer types found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve customer types",
                "error": str(e)
            }), 500


    #--- get all item categories ----#
    @app.route('/getcategories', methods=['GET'])
    def getcategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM physical_item_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve categories",
                "error": str(e)
            }), 500
        

    #--- get user to check if existing ----#
    @app.route('/getuser', methods=['GET'])
    def getuser():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        if 'user' in request.args:
            user = request.args['user']
        else:
            return "Error: No User field provided. Please specify it."
        
        if 'login_pw' in request.args:
            login_pw = request.args['login_pw']
        else:
            return "Error: No Password provided. Please specify it."

        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.id AS id, a.user AS user, a.built_in AS built_in, a.built_in_password AS built_in_password, a.oauth AS oauth, a.status AS status, COALESCE(b.firstname, 'none') AS firstname, COALESCE(b.middlename, 'none') AS middlename, COALESCE(b.lastname, 'none') AS lastname FROM app_users a LEFT JOIN customers b ON a.user = b.email_address WHERE a.user = %s AND a.org_code = %s AND a.status = %s"""
            data1 = (user, org_code, 1)
            
            cur.execute(sql1, data1)
            result = cur.fetchone()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                #if login_pw.strip() != "":
                '''
                login_pw = (login_pw or "").strip()
                if login_pw:
                    hashed_password = result["built_in_password"]
                    is_match = verify_password(login_pw, hashed_password)  # Check password match

                    if is_match:
                        return jsonify({
                            "message": "User retrieved successfully",
                            "data": result,
                            "status": "valid password"
                        }), 200
                    else:
                        return jsonify({
                            "message": "Invalid password",
                            "data": result,
                            "status": "invalid password"
                        }), 401
                else:
                '''
                return jsonify({
                    "message": "User retrieved successfully",
                    "data": result,
                    "status": "valid"
                }), 200
                        
            else:
                return jsonify({
                    "message": "No user found",
                    "data": [],
                    "status": "no user found"
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve user",
                "data": str(e),
                "status": "error"
            }), 500
            

    # to verify password
    def verify_password(login_pw: str, hashed_pw: str) -> bool:
        """Checks if the provided login password matches the hashed password."""
        return bcrypt.checkpw(login_pw.encode(), hashed_pw.encode())
    

    #--- get user roles ----#
    @app.route('/getuserroles', methods=['GET'])
    def getuserroles():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        if 'user' in request.args:
            user = request.args['user']
        else:
            return "Error: No User field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM app_user_roles WHERE user = %s AND org_code = %s AND STATUS = %s"""
            data1 = (user, org_code, 1)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "User Roles retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No user roles found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve user roles",
                "error": str(e)
            }), 500


    #--- get all services ----#
    @app.route('/getservices', methods=['GET'])
    def getservices():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """
                SELECT 
                    a.service_id,
                    a.description AS service_desc,
                    a.instruction AS instruction,
                    JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'detail_id', b.detail_id,
                            'detail_desc', b.description
                        )
                    ) AS service_details
                FROM services a
                LEFT JOIN service_details b ON a.service_id = b.service_id
                WHERE a.status = %s AND a.org_code = %s 
                GROUP BY a.service_id, a.description
                ORDER BY a.sequence ASC
            """
            
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            raw_result = cur.fetchall()  # Fetch all rows
            
            # Parse service_details JSON string into Python objects
            formatted_result = []
            for row in raw_result:
                # Convert `service_details` JSON string to a Python object
                try:
                    row['service_details'] = json.loads(row['service_details'])
                except json.JSONDecodeError:
                    row['service_details'] = []  # Default to empty list if parsing fails
                
                formatted_result.append(row)
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if formatted_result:
                return jsonify({
                    "message": "Services retrieved successfully",
                    "result": formatted_result
                }), 200
            else:
                return jsonify({
                    "message": "No services found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve services",
                "error": str(e)
            }), 500


    #--- get requested services per work request ----#
    @app.route('/getrequestedservices', methods=['GET'])
    def getrequestedservices():
        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No WR Id field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """
                SELECT 
                    a.service_id,
                    b.description AS service_desc,
                    JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'detail_id', c.detail_id,
                            'detail_desc', c.description,
                            'remarks', a.remarks
                        )
                    ) AS service_details
                FROM requested_services a
                LEFT JOIN services b ON a.service_id = b.service_id
                LEFT JOIN service_details c ON a.detail_id = c.detail_id
                WHERE a.wr_id = %s AND a.org_code = %s 
                GROUP BY a.service_id, b.description;
            """
            
            data1 = (wr_id, org_code)
            
            cur.execute(sql1, data1)
            raw_result = cur.fetchall()  # Fetch all rows
            
            # Parse service_details JSON string into Python objects
            formatted_result = []
            for row in raw_result:
                # Convert `service_details` JSON string to a Python object
                try:
                    row['service_details'] = json.loads(row['service_details'])
                except json.JSONDecodeError:
                    row['service_details'] = []  # Default to empty list if parsing fails
                
                formatted_result.append(row)
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if formatted_result:
                return jsonify({
                    "message": "Requested Services retrieved successfully",
                    "result": formatted_result
                }), 200
            else:
                return jsonify({
                    "message": "No requested services found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve requested services",
                "error": str(e)
            }), 500


    #--- get saved planners per work request ----#
    @app.route('/getsavedplanners', methods=['GET'])
    def getsavedplanners():
        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No WR Id field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """
                SELECT 
                    a.user AS user,
                    CONCAT(b.firstname, ' ', b.lastname) AS name 
                FROM work_order_team a
                LEFT JOIN app_users b 
                ON a.user = b.user
                WHERE role = %s AND a.wr_id = %s AND a.org_code = %s 
            """
            
            data1 = ("planner", wr_id, org_code)
            
            cur.execute(sql1, data1)
            raw_result = cur.fetchall()  # Fetch all rows
            
            # Parse service_details JSON string into Python objects
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if raw_result:
                return jsonify({
                    "message": "Saved Planners retrieved successfully",
                    "result": raw_result
                }), 200
            else:
                return jsonify({
                    "message": "No saved planners found",
                    "result": []
                }), 404
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve saved planners",
                "error": str(e)
            }), 500


    #--- get saved pre-approver per work request ----#
    @app.route('/getsavedpreapprover', methods=['GET'])
    def getsavedpreapprover():
        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No WR Id field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """
                SELECT 
                    a.user AS user,
                    CONCAT(b.firstname, ' ', b.lastname) AS name 
                FROM work_order_team a
                LEFT JOIN app_users b 
                ON a.user = b.user
                WHERE role = %s AND a.wr_id = %s AND a.org_code = %s 
            """
            
            data1 = ("team lead", wr_id, org_code)
            
            cur.execute(sql1, data1)
            raw_result = cur.fetchall()  # Fetch all rows
            
            # Parse service_details JSON string into Python objects
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if raw_result:
                return jsonify({
                    "message": "Saved Pre-Approver retrieved successfully",
                    "result": raw_result
                }), 200
            else:
                return jsonify({
                    "message": "No saved pre-approver found",
                    "result": []
                }), 404
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve saved pre-approver",
                "error": str(e)
            }), 500    
    

    #--- get saved final approver per work request ----#
    @app.route('/getsavedfinalapprover', methods=['GET'])
    def getsavedfinalapprover():
        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No WR Id field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """
                SELECT 
                    a.user AS user,
                    CONCAT(b.firstname, ' ', b.lastname) AS name 
                FROM work_order_team a
                LEFT JOIN app_users b 
                ON a.user = b.user
                WHERE role = %s AND a.wr_id = %s AND a.org_code = %s 
            """
            
            data1 = ("manager", wr_id, org_code)
            
            cur.execute(sql1, data1)
            raw_result = cur.fetchall()  # Fetch all rows
            
            # Parse service_details JSON string into Python objects
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if raw_result:
                return jsonify({
                    "message": "Saved Final Approver retrieved successfully",
                    "result": raw_result
                }), 200
            else:
                return jsonify({
                    "message": "No saved final approver found",
                    "result": []
                }), 404
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve saved final approver",
                "error": str(e)
            }), 500    
        

    #--- get saved planners per work order ----#
    '''
    @app.route('/getsavedplannerswo', methods=['GET'])
    def getsavedplannerswo():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """
                SELECT 
                    a.user AS user,
                    CONCAT(b.firstname, ' ', b.lastname) AS name 
                FROM work_order_team a
                LEFT JOIN app_users b 
                ON a.user = b.user
                WHERE a.wo_number = %s AND a.org_code = %s 
            """
            
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            raw_result = cur.fetchall()  # Fetch all rows
            
            # Parse service_details JSON string into Python objects
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if raw_result:
                return jsonify({
                    "message": "Saved Planners retrieved successfully",
                    "result": raw_result
                }), 200
            else:
                return jsonify({
                    "message": "No saved planners found",
                    "result": []
                }), 404
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve saved planners",
                "error": str(e)
            }), 500
    '''

    #--- get attached files per work request ----#
    @app.route('/getattachmentswr', methods=['GET'])
    def getattachmentswr():
        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No WR Id field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT * FROM wr_attachments WHERE wr_id = %s AND org_code = %s"""
            
            data1 = (wr_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Attachments retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No attachments found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve attachments",
                "error": str(e)
            }), 500


    #--- get attached files per work order ----#
    @app.route('/getattachmentswo', methods=['GET'])
    def getattachmentswo():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT * FROM wo_attachments WHERE wo_number = %s AND org_code = %s"""
            
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Attachments retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No attachments found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve attachments",
                "error": str(e)
            }), 500
        

    #--- get more info per work request ----#
    @app.route('/getmoreinfo', methods=['GET'])
    def getmoreinfo():
        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No WR Id field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """
                    SELECT 
                        a.wr_id AS wr_id,
                        a.wr_code AS wr_code, 
                        a.firstname AS firstname,
                        a.middlename AS middlename,
                        a.lastname AS lastname,
                        a.email_address AS email_address,
                        a.business_unit AS business_unit, 
                        e.description AS business_unit_desc, 
                        a.customer_type AS customer_type_code,
                        b.description AS customer_type, 
                        a.project_location AS project_location,
                        DATE_FORMAT(a.submitted_datetime, '%%M %%d, %%Y') AS submitted_datetime,
                        DATE_FORMAT(a.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        a.project_desc AS project_desc,
                        a.project_details AS project_details,
                        a.submitted_datetime AS submitted_datetime,
                        a.status AS status, 
                        a.org_code AS org_code 
                    FROM 
                        work_requests a
                    LEFT JOIN 
                        customer_types b ON a.customer_type = b.code
                    LEFT JOIN
                        business_units e ON a.business_unit = e.code 
                    WHERE a.wr_id = %s AND a.org_code = %s 
                """
            
            data1 = (wr_id, org_code)
            cur.execute(sql1, data1)
            result = cur.fetchall()

            # Add logic to fetch and consolidate smart_summary
            if result:
                sql2 = """
                    SELECT GROUP_CONCAT(smart_summary SEPARATOR '\n\n') AS smart_summary
                    FROM wr_attachments
                    WHERE wr_id = %s AND smart_summary IS NOT NULL AND TRIM(smart_summary) != ''
                """
                cur.execute(sql2, (wr_id,))
                summary_row = cur.fetchone()
                smart_summary = summary_row['smart_summary'] if summary_row else None

                result[0]['smart_summary'] = smart_summary or ''  # Inject into first (and only) record

                app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
                return jsonify({
                    "message": "More Info retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No more info found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve more info",
                "error": str(e)
            }), 500



    #--- get messages per work request ----#
    @app.route('/getmessages', methods=['GET'])
    def getmessages():
        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No WR Id field provided. Please specify it."

        if 'task_gid' in request.args:
            task_gid = request.args['task_gid']
        else:
            return "Error: No Task GID field provided. Please specify it."

        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            # for asana chat viewed per work order
            if task_gid != "" and task_gid is not None and task_gid != "null":
                sql1 = """SELECT project_gid, task_gid, task_name, message,created_datetime, created_by, source, read_datetime, wo_code FROM app_chatbox WHERE task_gid = %s AND org_code = %s ORDER BY created_datetime"""
                data1 = (task_gid, org_code)
            # for asana chat viewed per work request (if task_gid is not provided)
            else:
                sql1 = """SELECT a.project_gid AS project_gid, a.task_gid AS task_gid, a.task_name AS task_name, a.message AS message, a.created_datetime AS created_datetime, a.created_by AS created_by, a.source AS source, a.read_datetime AS read_datetime, a.wo_code AS wo_code FROM app_chatbox a JOIN work_requests b ON a.project_gid = b.project_gid WHERE b.wr_id = %s AND a.org_code = %s ORDER BY created_datetime"""
                data1 = (wr_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Messages retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No messages found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve messages",
                "error": str(e)
            }), 500


    #--- get messages intended for user logged in ----#
    @app.route('/getusermessages', methods=['GET'])
    def getusermessages():
        if 'user_login' in request.args:
            user_login = request.args['user_login']
        else:
            return "Error: No User Login field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT title, message, created_datetime, created_by, source, action_url, status, priority, read_datetime FROM app_inbox WHERE recipient = %s AND org_code = %s ORDER BY created_datetime DESC"""
            
            data1 = (user_login, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Messages retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No messages found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve messages",
                "error": str(e)
            }), 500


    #--- get unread messages count intended for user logged in ----#
    @app.route('/getuserunreadscount', methods=['GET'])
    def getuserunreadscount():
        if 'user_login' in request.args:
            user_login = request.args['user_login']
        else:
            return "Error: No User Login field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT count(*) AS count FROM app_inbox WHERE recipient = %s AND org_code = %s AND status = %s"""
            
            data1 = (user_login, org_code, "unread")
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Unreads Count retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No unreads count",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve unreads count",
                "error": str(e)
            }), 500
        

    #--- get all business units ----#
    @app.route('/getbusinessunits', methods=['GET'])
    def getbusinessunits():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM business_units WHERE status = %s AND org_code = %s ORDER BY description"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Business Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No business units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve business units",
                "error": str(e)
            }), 500


    #--- get all scope list ----#
    @app.route('/getscopelist', methods=['GET'])
    def getscopelist():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM services WHERE status = %s AND org_code = %s ORDER BY description"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Scope list retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No scope list found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve scope list",
                "error": str(e)
            }), 500


    #--- get all physical cu categories ----#
    @app.route('/getphysicalcucategories', methods=['GET'])
    def getphysicalcucategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM physical_cu_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU Categories",
                "error": str(e)
            }), 500


    #--- get all labor cu categories ----#
    @app.route('/getlaborcucategories', methods=['GET'])
    def getlaborcucategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM human_cu_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU Categories",
                "error": str(e)
            }), 500


    #--- get all equipment cu categories ----#
    @app.route('/getequipmentcucategories', methods=['GET'])
    def getequipmentcucategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM equip_cu_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU Categories",
                "error": str(e)
            }), 500
        

    #--- get all physical item categories ----#
    @app.route('/getphysicalitemcategories', methods=['GET'])
    def getphysicalitemcategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM physical_item_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Item Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Item Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve Item Categories",
                "error": str(e)
            }), 500


    #--- get all labor categories ----#
    @app.route('/getlaborcategories', methods=['GET'])
    def getlaborcategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM human_item_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Labor Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Labor Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve Labor Categories",
                "error": str(e)
            }), 500


    #--- get all equipment categories ----#
    @app.route('/getequipmentcategories', methods=['GET'])
    def getequipmentcategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM equip_item_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Equipment Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Equipment Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve Equipment Categories",
                "error": str(e)
            }), 500
            
            
    #--- get all human cu categories ----#
    @app.route('/gethumancucategories', methods=['GET'])
    def gethumancucategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM human_cu_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU Categories",
                "error": str(e)
            }), 500


    #--- get all equipment cu categories ----#
    @app.route('/getequipcucategories', methods=['GET'])
    def getequipcucategories():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM equip_cu_categories WHERE status = %s AND org_code = %s"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Categories retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Categories found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU Categories",
                "error": str(e)
            }), 500
            

    #--- get all work request statuses ----#
    @app.route('/getwrstatuses', methods=['GET'])
    def getwrstatuses():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM work_request_statuses WHERE status = %s AND org_code = %s ORDER BY sequence"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Request Statuses retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work request statuses found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work request statuses",
                "error": str(e)
            }), 500
        

    #--- get all work request statuses ----#
    @app.route('/getwrstatuseslimited', methods=['GET'])
    def getwrstatuseslimited():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'status_val' in request.args:
            status_val = request.args['status_val']
        else:
            return "Error: No Status field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            if status_val == "Accepted":
                sql1 = """SELECT * FROM work_request_statuses WHERE description IN ('Closed') AND status = %s AND org_code = %s ORDER BY sequence"""
            elif status_val == "Team Assigned":
                sql1 = """SELECT * FROM work_request_statuses WHERE description IN ('Accepted', 'Closed', 'Declined', 'On Hold') AND status = %s AND org_code = %s ORDER BY sequence"""
            elif status_val == "Queue":
                sql1 = """SELECT * FROM work_request_statuses WHERE description IN ('Team Assigned', 'Closed', 'Declined', 'On Hold') AND status = %s AND org_code = %s ORDER BY sequence"""
            elif status_val == "On Hold":
                sql1 = """SELECT * FROM work_request_statuses WHERE description IN ('Team Assigned', 'Closed', 'Declined') AND status = %s AND org_code = %s ORDER BY sequence"""
            else:
                #sql1 = """SELECT * FROM work_request_statuses WHERE status = %s AND org_code = %s ORDER BY sequence"""
                sql1 = """SELECT * FROM work_request_statuses WHERE 1=0"""

            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Request Statuses retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work request statuses found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work request statuses",
                "error": str(e)
            }), 500
        

    #--- get all work orders statuses with show_lov is true ----#
    @app.route('/getwostatuses', methods=['GET'])
    def getwostatuses():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM work_order_statuses WHERE show_lov = %s AND org_code = %s ORDER BY sequence"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Statuses retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order statuses found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order statuses",
                "error": str(e)
            }), 500


    #--- get all work orders statuses ----#
    @app.route('/getwostatusesall', methods=['GET'])
    def getwostatusesall():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM work_order_statuses WHERE org_code = %s ORDER BY sequence"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Statuses retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order statuses found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order statuses",
                "error": str(e)
            }), 500


    #--- get all proposal statuses ----#
    @app.route('/getproposalstatusesall', methods=['GET'])
    def getproposalstatusesall():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM proposal_statuses WHERE org_code = %s ORDER BY sequence"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Proposal Statuses retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No proposal statuses found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve proposal statuses",
                "error": str(e)
            }), 500    


    #--- get work orders statuses: Executed, Billed, Closed only ----#
    @app.route('/getwostatuseslimited', methods=['GET'])
    def getwostatuseslimited():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'status_val' in request.args:
            status_val = request.args['status_val']
        else:
            return "Error: No Status field provided. Please specify it."

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            if status_val == "New":
                sql1 = """SELECT * FROM work_order_statuses WHERE description IN ('Started', 'In Progress','Completed', 'Cancelled', 'On-hold') AND org_code = %s ORDER BY sequence"""
            elif status_val == "Started":
                sql1 = """SELECT * FROM work_order_statuses WHERE description IN ('In Progress', 'Completed', 'Cancelled', 'On-hold') AND org_code = %s ORDER BY sequence"""
            elif status_val == "In Progress":
                sql1 = """SELECT * FROM work_order_statuses WHERE description IN ('Completed', 'Cancelled', 'On-hold') AND org_code = %s ORDER BY sequence"""
            else:
                sql1 = """SELECT * FROM work_order_statuses WHERE description IN ('Completed') AND org_code = %s ORDER BY sequence"""

            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Statuses retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order statuses found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order statuses",
                "error": str(e)
            }), 500

    #--- get all WO priority levels ----#
    @app.route('/getprioritylevels', methods=['GET'])
    def getprioritylevels():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM priority_levels WHERE status = %s AND org_code = %s ORDER BY sequence"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Priority Levels retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No priority levels found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve priority levels",
                "error": str(e)
            }), 500


    #--- get all WR priority levels ----#
    @app.route('/getwrprioritylevels', methods=['GET'])
    def getwrprioritylevels():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM wr_priority_levels WHERE status = %s AND org_code = %s ORDER BY sequence"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Priority Levels retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No priority levels found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve priority levels",
                "error": str(e)
            }), 500


    #--- get all planners ----#
    @app.route('/getplanners', methods=['GET'])
    def getplanners():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.user AS code, CONCAT(b.firstname, ' ', b.lastname) AS name FROM app_user_roles a LEFT JOIN app_users b ON a.user = b.user WHERE a.role = %s AND a.status = %s AND a.org_code = %s ORDER BY name"""
            data1 = ("planner", 1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Planners retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No planners found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve planners",
                "error": str(e)
            }), 500


    #--- get all project names ----#
    '''
    @app.route('/getprojectnames', methods=['GET'])
    def getprojectnames():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT * FROM project_names WHERE status = %s AND org_code = %s ORDER BY sequence"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Project Names retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No project names found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve project names",
                "error": str(e)
            }), 500
    '''
    # --- get all project names ----#
    @app.route('/getprojectnames', methods=['GET'])
    def getprojectnames():
        conn = None
        cur = None
        try:
            if 'org_code' in request.args:
                org_code = request.args['org_code']
            else:
                return jsonify({
                    "message": "No Organization Code field provided",
                    "result": []
                }), 400

            # ✅ NEW: optional filter
            active_only = request.args.get('active_only', '1')  # "1" or "0"

            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql1 = """
                SELECT
                    project_id,
                    description,
                    status,
                    sequence,
                    org_code
                FROM project_names
                WHERE
                    org_code = %s
                    AND (%s = '0' OR status = 1)
                ORDER BY sequence, description
            """

            data1 = (org_code, active_only)

            cur.execute(sql1, data1)
            result = cur.fetchall()

            return jsonify({
                "message": "Project Names retrieved successfully",
                "result": result
            }), 200

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve project names",
                "error": str(e),
                "result": []
            }), 500

        finally:
            try:
                if cur:
                    cur.close()
            except:
                pass
            try:
                if conn:
                    conn.close()
            except:
                pass


    #--- get all users per role ----#
    @app.route('/getusersperrole', methods=['GET'])
    def getusersperrole():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'user_role' in request.args:
            user_role = request.args['user_role']
        else:
            return "Error: No Role field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            sql1 = """SELECT a.user AS user, a.role AS role, CONCAT(b.firstname, ' ', b.lastname) AS name FROM app_user_roles a LEFT JOIN app_users b ON a.user = b.user WHERE a.role = %s AND a.status = %s AND b.status = %s AND a.org_code = %s ORDER BY name"""
            data1 = (user_role, 1, 1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Users retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No users found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve users",
                "error": str(e)
            }), 500


    #--- get comments of certain work order ----#
    @app.route('/getwocomments', methods=['GET'])
    def getwocomments():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.wo_number AS wo_number, a.comments AS comments, a.commented_datetime AS commented_datetime, CONCAT(b.firstname, ' ', b.lastname) AS commented_by, a.commented_by AS commented_user FROM wo_comments a LEFT JOIN app_users b ON a.commented_by = b.user WHERE a.wo_number = %s AND a.org_code = %s ORDER BY a.commented_datetime DESC"""
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Comments retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order comments found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order comments",
                "error": str(e)
            }), 500


    #--- get approvals of certain work order ----#
    @app.route('/getwoapproval', methods=['GET'])
    def getwoapproval():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        if 'approval_status' in request.args:
            approval_status = request.args['approval_status']
        else:
            return "Error: No Work Order Approval Status field provided. Please specify it."

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT action_status FROM approval_requests WHERE txn_reference = %s AND org_code = %s AND action_status = %s"""
            data1 = (wo_number, org_code, approval_status)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Approvals retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order approvals found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order approvals",
                "error": str(e)
            }), 500


    #--- get approvals of certain work order ----#
    '''
    @app.route('/getwoforapproval', methods=['GET'])
    def getwoforapproval():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        if 'approval_type' in request.args:
            approval_type = request.args['approval_type']
        else:
            return "Error: No Work Order Approval Type field provided. Please specify it."

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT approval_type FROM approval_requests WHERE txn_reference = %s AND org_code = %s AND approval_type = %s"""
            data1 = (wo_number, org_code, approval_type)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Approval Types retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order approval types found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order approval types",
                "error": str(e)
            }), 500
    ''' 

    #--- get approval type of certain work order ----#
    @app.route('/getwoapprovaltype', methods=['GET'])
    def getwoapprovaltype():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        if 'approval_type' in request.args:
            approval_type = request.args['approval_type']
        else:
            return "Error: No Work Order Approval Type field provided. Please specify it."

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            '''
            sql1 = """SELECT approval_type FROM approval_requests WHERE txn_reference = %s AND org_code = %s AND approval_type = %s AND action_status != %s"""
            '''
            sql1 = """
                    SELECT approval_type
                    FROM approval_requests
                    WHERE txn_reference = %s
                    AND org_code = %s
                    AND approval_type = %s
                    AND (action_status IS NULL OR action_status != %s)
                """
            data1 = (wo_number, org_code, approval_type, 'Changes Requested')
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Approval Type retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order approval type found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order approval type",
                "error": str(e)
            }), 500
        

    #--- get file attachment type of certain work order ----#
    @app.route('/getwoattachmenttype', methods=['GET'])
    def getwoattachmenttype():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        if 'file_title' in request.args:
            file_title = request.args['file_title']
        else:
            return "Error: No File Attachment Type field provided. Please specify it."

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT file_title FROM wo_attachments WHERE wo_number = %s AND org_code = %s AND file_title = %s"""
            data1 = (wo_number, org_code, file_title)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order File Title retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order file title found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order file title",
                "error": str(e)
            }), 500
        

    #--- get team members of certain work request ----#
    @app.route('/getwrteam', methods=['GET'])
    def getwrteam():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No Work Request ID field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.id AS id, a.wo_number AS wo_number, a.user AS user, a.role AS role, a.assigned_datetime AS assigned_datetime, CONCAT(b.firstname, ' ', b.lastname) AS name FROM work_order_team a LEFT JOIN app_users b ON a.user = b.user WHERE a.wr_id = %s AND a.org_code = %s ORDER BY a.id"""
            data1 = (wr_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Request Team retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work request team found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work request team",
                "error": str(e)
            }), 500


    #--- get team members of certain work order ----#
    '''
    @app.route('/getwoteam', methods=['GET'])
    def getwoteam():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.id AS id, a.wo_number AS wo_number, a.user AS user, a.role AS role, a.assigned_datetime AS assigned_datetime, CONCAT(b.firstname, ' ', b.lastname) AS name FROM work_order_team a LEFT JOIN app_users b ON a.user = b.user WHERE a.wo_number = %s AND a.org_code = %s ORDER BY a.id"""
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Team retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order team found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order team",
                "error": str(e)
            }), 500
    '''     

    #--- get other statuses of certain work request from work order ----#
    @app.route('/getwrotherstatuses', methods=['GET'])
    def getwrotherstatuses():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wr_id' in request.args:
            wr_id = int(request.args['wr_id'])
        else:
            return "Error: No Work Request ID field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT wo_number, wo_code, status AS wo_status, proposal_status, 0 AS billing_status FROM work_orders WHERE wr_id = %s AND org_code = %s ORDER BY created_datetime"""
            data1 = (wr_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Request Other Statuses retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work request other statuses found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work request other statuses",
                "error": str(e)
            }), 500
        

    #--- get team members of certain work order ----#
    @app.route('/getwoteam', methods=['GET'])
    def getwoteam():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.id AS id, a.wo_number AS wo_number, a.user AS user, a.role AS role, a.assigned_datetime AS assigned_datetime, CONCAT(b.firstname, ' ', b.lastname) AS name FROM work_order_team a LEFT JOIN app_users b ON a.user = b.user WHERE a.wo_number = %s AND a.org_code = %s ORDER BY a.id"""
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Order Team retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order team found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order team",
                "error": str(e)
            }), 500


    #--- get all work orders (OLD)----#
    @app.route('/getworkorders_old', methods=['GET'])
    def getworkorders_old():
        if 'wo_type' in request.args:
            wo_type = request.args['wo_type']
        else:
            return "Error: No WO Type field provided. Please specify it."
        
        if 'status' in request.args:
            status = request.args['status']
        else:
            return "Error: No Status field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            # NOTE: MySQL syntax (uses DATE_FORMAT + GROUP_CONCAT)
            if status != "":
                sql1 = """
                    SELECT 
                        a.wo_number AS wo_number,
                        a.wr_id AS wr_id, 
                        b.wr_code AS wr_code, 
                        a.wo_code AS wo_code, 
                        a.wo_type AS wo_type, 
                        a.wo_description AS wo_description, 
                        a.job_start_date AS wo_job_start_date, 
                        a.job_end_date AS wo_job_end_date, 
                        a.status AS wo_status, 
                        a.business_unit AS business_unit, 
                        bu.description AS company,
                        e.description AS wo_priority_level, 
                        e.code AS wo_priority_level_code, 
                        a.created_datetime AS wo_created_datetime, 
                        a.due_date AS wo_due_date, 
                        a.revenue AS revenue, 
                        a.actual_total_cost AS actual_total_cost, 
                        a.gross_profit AS gross_profit, 
                        a.cost_type_used AS cost_type_used, 
                        CONCAT(d.firstname, ' ', d.lastname) AS wo_planner, 
                        CONCAT(LEFT(g.firstname,1), ' ', g.lastname) AS initiator, 
                        d.user AS wo_planner_code, 
                        a.location AS wo_location, 
                        a.project_name AS project_name, 
                        a.project_description AS project_description, 
                        a.project_gid AS wo_project_gid, 
                        a.wr_id AS wr_id, 
                        a.org_code AS org_code, 
                        b.firstname AS firstname,
                        b.middlename AS middlename,
                        b.lastname AS lastname,
                        b.email_address AS email_address,
                        b.project_location AS project_location,
                        DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        b.project_desc AS project_desc,
                        b.project_details AS project_details,
                        c.description AS customer_type, 
                        h.service_id AS service_id,
                        s.description AS scope,

                        -- CONCATENATED sub-scope from service_details (via requested_services.detail_id)
                        GROUP_CONCAT(
                            DISTINCT sd.description
                            ORDER BY sd.description
                            SEPARATOR ', '
                        ) AS sub_scope,

                        i.total_cost AS total_cost,
                        i.total_cost_low AS total_cost_low,
                        i.total_cost_avg AS total_cost_avg,

                        -- chatbox count can multiply because of requested_services join, so use DISTINCT
                        COUNT(DISTINCT f.id) AS unread_count,

                        -- latest approval request (ONLY 2 columns requested)
                        ar_last.txn_reference AS approval_txn_reference,
                        ar_last.action_status AS approval_action_status

                    FROM 
                        work_orders a 
                    LEFT JOIN
                        work_requests b 
                    ON 
                        a.wr_id = b.wr_id
                    LEFT JOIN 
                        customer_types c  
                    ON 
                        b.customer_type = c.code
                    LEFT JOIN 
                        app_users d 
                    ON 
                        a.planner = d.user 
                    LEFT JOIN 
                        priority_levels e 
                    ON 
                        a.priority_level = e.code 
                    LEFT JOIN 
                        app_chatbox f 
                    ON 
                        b.project_gid = f.project_gid AND f.read_datetime IS NULL 
                    LEFT JOIN 
                        app_users g 
                    ON 
                        b.email_address = g.user 

                    LEFT JOIN 
                        requested_services h
                    ON
                        a.wr_id = h.wr_id
                    LEFT JOIN
                        services s
                    ON
                        h.service_id = s.service_id
                    LEFT JOIN
                        service_details sd
                    ON
                        h.detail_id = sd.detail_id
                    LEFT JOIN 
                        wo_cost_estimates i
                    ON
                        a.wo_number = i.wo_number 
                    LEFT JOIN
                        business_units bu
                    ON
                        a.business_unit = bu.code

                    -- latest approval_requests row per WO (by MAX(id))
                    LEFT JOIN (
                        SELECT ar.txn_reference, ar.action_status
                        FROM approval_requests ar
                        INNER JOIN (
                            SELECT txn_reference, MAX(id) AS max_id
                            FROM approval_requests
                            GROUP BY txn_reference
                        ) x
                        ON x.txn_reference = ar.txn_reference
                        AND x.max_id = ar.id
                    ) ar_last
                    ON ar_last.txn_reference = a.wo_number

                    WHERE 
                        a.wo_type = %s 
                    AND
                        a.status = %s 
                    AND 
                        a.org_code = %s 

                    GROUP BY 
                        a.wo_number, a.wr_id, b.wr_code, a.wo_code, a.wo_type, a.wo_description,
                        a.job_start_date, a.job_end_date, a.status, a.business_unit,
                        e.description, e.code, a.created_datetime, a.due_date, a.revenue,
                        a.actual_total_cost, a.gross_profit, a.cost_type_used,
                        d.firstname, d.lastname, g.firstname, g.lastname, d.user,
                        a.location, a.project_name, a.project_description, a.project_gid,
                        a.org_code,
                        b.firstname, b.middlename, b.lastname, b.email_address,
                        b.project_location, b.proposal_deadline, b.job_start_date, b.job_end_date,
                        b.project_desc, b.project_details, c.description,
                        i.total_cost, i.total_cost_low, i.total_cost_avg,
                        ar_last.txn_reference, ar_last.action_status

                    ORDER BY 
                        a.created_datetime DESC
                """
                data1 = (wo_type, status, org_code)

            else:
                sql1 = """
                    SELECT 
                        a.wo_number AS wo_number,
                        a.wo_code AS wo_code, 
                        a.wr_id AS wr_id, 
                        b.wr_code AS wr_code, 
                        a.wo_type AS wo_type, 
                        a.wo_description AS wo_description, 
                        a.job_start_date AS wo_job_start_date, 
                        a.job_end_date AS wo_job_end_date, 
                        a.status AS wo_status, 
                        a.business_unit AS business_unit, 
                        bu.description AS company,
                        e.description AS wo_priority_level, 
                        e.code AS wo_priority_level_code, 
                        a.created_datetime AS wo_created_datetime, 
                        a.due_date AS wo_due_date, 
                        a.revenue AS revenue, 
                        a.actual_total_cost AS actual_total_cost, 
                        a.gross_profit AS gross_profit, 
                        a.cost_type_used AS cost_type_used, 
                        CONCAT(d.firstname, ' ', d.lastname) AS wo_planner, 
                        CONCAT(LEFT(g.firstname,1), ' ', g.lastname) AS initiator, 
                        d.user AS wo_planner_code, 
                        a.location AS wo_location, 
                        a.project_name AS project_name, 
                        a.project_description AS project_description, 
                        a.project_gid AS wo_project_gid, 
                        a.wr_id AS wr_id, 
                        a.org_code AS org_code, 
                        b.firstname AS firstname,
                        b.middlename AS middlename,
                        b.lastname AS lastname,
                        b.email_address AS email_address,
                        b.project_location AS project_location,
                        DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        b.project_desc AS project_desc,
                        b.project_details AS project_details,
                        c.description AS customer_type, 
                        h.service_id AS service_id,
                        s.description AS scope,
                        -- CONCATENATED sub-scope from service_details
                        GROUP_CONCAT(
                            DISTINCT sd.description
                            ORDER BY sd.description
                            SEPARATOR ', '
                        ) AS sub_scope,

                        i.total_cost AS total_cost,
                        i.total_cost_low AS total_cost_low,
                        i.total_cost_avg AS total_cost_avg,

                        -- avoid multiplication due to requested_services join
                        COUNT(DISTINCT f.id) AS unread_count,

                        -- latest approval request (ONLY 2 columns requested)
                        ar_last.txn_reference AS approval_txn_reference,
                        ar_last.action_status AS approval_action_status

                    FROM 
                        work_orders a 
                    LEFT JOIN
                        work_requests b 
                    ON 
                        a.wr_id = b.wr_id
                    LEFT JOIN 
                        customer_types c  
                    ON 
                        b.customer_type = c.code
                    LEFT JOIN 
                        app_users d 
                    ON 
                        a.planner = d.user  
                    LEFT JOIN 
                        priority_levels e 
                    ON 
                        a.priority_level = e.code 
                    LEFT JOIN 
                        app_chatbox f 
                    ON 
                        b.project_gid = f.project_gid AND f.read_datetime IS NULL 
                    LEFT JOIN 
                        app_users g 
                    ON 
                        b.email_address = g.user 

                    LEFT JOIN 
                        requested_services h
                    ON
                        a.wr_id = h.wr_id 
                    LEFT JOIN
                        services s
                    ON
                        h.service_id = s.service_id
                    LEFT JOIN
                        service_details sd
                    ON
                        h.detail_id = sd.detail_id
                    LEFT JOIN 
                        wo_cost_estimates i
                    ON
                        a.wo_number = i.wo_number 
                    LEFT JOIN
                        business_units bu
                    ON
                        a.business_unit = bu.code

                    -- latest approval_requests row per WO (by MAX(id))
                    LEFT JOIN (
                        SELECT ar.txn_reference, ar.action_status
                        FROM approval_requests ar
                        INNER JOIN (
                            SELECT txn_reference, MAX(id) AS max_id
                            FROM approval_requests
                            GROUP BY txn_reference
                        ) x
                        ON x.txn_reference = ar.txn_reference
                        AND x.max_id = ar.id
                    ) ar_last
                    ON ar_last.txn_reference = a.wo_number

                    WHERE 
                        a.wo_type = %s 
                    AND
                        a.org_code = %s 

                    GROUP BY 
                        a.wo_number, a.wr_id, b.wr_code, a.wo_code, a.wo_type, a.wo_description,
                        a.job_start_date, a.job_end_date, a.status, a.business_unit,
                        e.description, e.code, a.created_datetime, a.due_date, a.revenue,
                        a.actual_total_cost, a.gross_profit, a.cost_type_used,
                        d.firstname, d.lastname, g.firstname, g.lastname, d.user,
                        a.location, a.project_name, a.project_description, a.project_gid,
                        a.org_code,
                        b.firstname, b.middlename, b.lastname, b.email_address,
                        b.project_location, b.proposal_deadline, b.job_start_date, b.job_end_date,
                        b.project_desc, b.project_details, c.description,
                        i.total_cost, i.total_cost_low, i.total_cost_avg,
                        ar_last.txn_reference, ar_last.action_status

                    ORDER BY 
                        a.created_datetime DESC
                """
                data1 = (wo_type, org_code)

            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are work requests
            if result:
                return jsonify({
                    "message": "Work Orders retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work orders found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work orders",
                "error": str(e)
            }), 500
    
    
    #--- get all work orders ----#
    @app.route('/getworkorders', methods=['GET'])
    def getworkorders():
        if 'wo_type' in request.args:
            wo_type = request.args['wo_type']
        else:
            return "Error: No WO Type field provided. Please specify it."

        if 'status' in request.args:
            status = request.args['status']
        else:
            return "Error: No Status field provided. Please specify it."

        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        # ✅ NEW: identity + "My Work Orders" switch
        email = request.args.get('email', '').strip()              # userLogin email
        my_only = request.args.get('my_only', '0').strip()         # 1 = My Work Orders

        # ✅ NEW: optional server-side filters
        business_unit = request.args.get('business_unit', '').strip()  # BU code
        wo_status_filter = request.args.get('wo_status', '').strip()   # status text

        # ✅ NEW: optional WR multi-select filter (CSV: "12,15,21")
        wr_ids_raw = (request.args.get('wr_ids') or '').strip()
        wr_ids = []
        if wr_ids_raw:
            for x in wr_ids_raw.split(','):
                x = x.strip()
                if x.isdigit():
                    wr_ids.append(int(x))
        # wr_ids = [] means "no WR filter"

        # ✅ pagination
        try:
            offset = int(request.args.get('offset', 0))
        except:
            offset = 0

        try:
            limit = int(request.args.get('limit', 12))
        except:
            limit = 12

        if offset < 0:
            offset = 0
        if limit <= 0:
            limit = 12

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            # helper: build IN clause safely
            def _in_clause(values):
                # returns: ("(%s,%s,...)", [vals...]) OR ("", [])
                if not values:
                    return "", []
                placeholders = ",".join(["%s"] * len(values))
                return f"({placeholders})", list(values)

            wr_in_sql, wr_in_params = _in_clause(wr_ids)

            # ----------------------------
            # ✅ TOTAL COUNT (paging-safe)
            # requester OR planner (from work_order_team)
            # ----------------------------
            if status != "":
                sql_count = """
                    SELECT COUNT(DISTINCT a.wo_number) AS total
                    FROM work_orders a
                    LEFT JOIN work_requests b
                        ON a.wr_id = b.wr_id
                    WHERE a.wo_type = %s
                    AND a.status = %s
                    AND a.org_code = %s
                """
                data_count = [wo_type, status, org_code]

                if business_unit != "":
                    sql_count += " AND a.business_unit = %s"
                    data_count.append(business_unit)

                # ✅ NEW: WR filter
                if wr_in_sql:
                    sql_count += f" AND a.wr_id IN {wr_in_sql}"
                    data_count.extend(wr_in_params)

                # ✅ My Work Orders filter
                sql_count += """
                    AND (
                        %s = '0'
                        OR b.email_address = %s
                        OR EXISTS (
                            SELECT 1
                            FROM work_order_team wt
                            WHERE wt.wr_id = a.wr_id
                            AND wt.role = 'planner'
                            AND wt.user = %s
                        )
                    )
                """
                data_count.extend([my_only, email, email])
                data_count = tuple(data_count)

            else:
                sql_count = """
                    SELECT COUNT(DISTINCT a.wo_number) AS total
                    FROM work_orders a
                    LEFT JOIN work_requests b
                        ON a.wr_id = b.wr_id
                    WHERE a.wo_type = %s
                    AND a.org_code = %s
                """
                data_count = [wo_type, org_code]

                if business_unit != "":
                    sql_count += " AND a.business_unit = %s"
                    data_count.append(business_unit)

                if wo_status_filter != "":
                    sql_count += " AND a.status = %s"
                    data_count.append(wo_status_filter)

                # ✅ NEW: WR filter
                if wr_in_sql:
                    sql_count += f" AND a.wr_id IN {wr_in_sql}"
                    data_count.extend(wr_in_params)

                # ✅ My Work Orders filter
                sql_count += """
                    AND (
                        %s = '0'
                        OR b.email_address = %s
                        OR EXISTS (
                            SELECT 1
                            FROM work_order_team wt
                            WHERE wt.wr_id = a.wr_id
                            AND wt.role = 'planner'
                            AND wt.user = %s
                        )
                    )
                """
                data_count.extend([my_only, email, email])
                data_count = tuple(data_count)

            cur.execute(sql_count, data_count)
            total_row = cur.fetchone()
            total = int(total_row["total"]) if total_row and "total" in total_row else 0

            # ----------------------------
            # ✅ MAIN QUERY (data rows)
            # planner comes from work_order_team via derived table
            # revenue comes from SUM(wo_revenues.amount) via derived table
            # ----------------------------
            if status != "":
                sql1 = """
                    SELECT 
                        a.wo_number AS wo_number,
                        a.wr_id AS wr_id, 
                        b.wr_code AS wr_code, 
                        a.wo_code AS wo_code, 
                        a.wo_type AS wo_type, 
                        a.wo_description AS wo_description, 
                        a.job_start_date AS wo_job_start_date, 
                        a.job_end_date AS wo_job_end_date, 
                        a.status AS wo_status, 
                        a.business_unit AS business_unit, 
                        bu.description AS company,
                        bu.acronym AS company_acronym, 
                        e.description AS wo_priority_level, 
                        e.code AS wo_priority_level_code, 
                        a.created_datetime AS wo_created_datetime, 
                        a.due_date AS wo_due_date, 

                        -- ✅ revenue from wo_revenues instead of work_orders.revenue
                        COALESCE(wor.revenue, 0) AS revenue,

                        a.actual_total_cost AS actual_total_cost, 
                        a.gross_profit AS gross_profit, 
                        a.cost_type_used AS cost_type_used, 

                        CONCAT(d.firstname, ' ', d.lastname) AS wo_planner, 
                        CONCAT(LEFT(g.firstname,1), ' ', g.lastname) AS initiator, 

                        -- ✅ planner email/login from work_order_team
                        wotp.planner AS wo_planner_code,

                        a.location AS wo_location, 
                        a.project_name AS project_name, 
                        a.project_description AS project_description, 
                        a.project_gid AS wo_project_gid, 
                        a.task_gid AS task_gid, 
                        a.org_code AS org_code, 

                        b.firstname AS firstname,
                        b.middlename AS middlename,
                        b.lastname AS lastname,
                        b.email_address AS email_address,
                        b.project_location AS project_location,
                        DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        b.project_desc AS project_desc,
                        b.project_details AS project_details,

                        c.description AS customer_type, 
                        h.service_id AS service_id,
                        s.description AS scope,

                        GROUP_CONCAT(
                            DISTINCT sd.description
                            ORDER BY sd.description
                            SEPARATOR ', '
                        ) AS sub_scope,

                        i.total_cost AS total_cost,
                        i.total_cost_low AS total_cost_low,
                        i.total_cost_avg AS total_cost_avg,

                        COUNT(DISTINCT f.id) AS unread_count,

                        ar_last.txn_reference AS approval_txn_reference,
                        ar_last.action_status AS approval_action_status

                    FROM 
                        work_orders a 
                    LEFT JOIN
                        work_requests b 
                            ON a.wr_id = b.wr_id
                    LEFT JOIN 
                        customer_types c  
                            ON b.customer_type = c.code
                    LEFT JOIN 
                        app_users d 
                            ON a.planner = d.user 
                    LEFT JOIN 
                        priority_levels e 
                            ON a.priority_level = e.code 
                    LEFT JOIN 
                        app_chatbox f 
                            ON b.project_gid = f.project_gid AND f.read_datetime IS NULL 
                    LEFT JOIN 
                        app_users g 
                            ON b.email_address = g.user 

                    LEFT JOIN 
                        requested_services h
                            ON a.wr_id = h.wr_id
                    LEFT JOIN
                        services s
                            ON h.service_id = s.service_id
                    LEFT JOIN
                        service_details sd
                            ON h.detail_id = sd.detail_id
                    LEFT JOIN 
                        wo_cost_estimates i
                            ON a.wo_number = i.wo_number 
                    LEFT JOIN
                        business_units bu
                            ON a.business_unit = bu.code

                    -- ✅ planner derived table (1 row per wr_id)
                    LEFT JOIN (
                        SELECT 
                            wr_id,
                            MAX(user) AS planner
                        FROM work_order_team
                        WHERE role = 'planner'
                        GROUP BY wr_id
                    ) wotp
                        ON wotp.wr_id = a.wr_id

                    -- ✅ revenue derived table: SUM(amount) per wo_number
                    LEFT JOIN (
                        SELECT
                            wo_number,
                            SUM(amount) AS revenue
                        FROM wo_revenues
                        GROUP BY wo_number
                    ) wor
                        ON wor.wo_number = a.wo_number

                    LEFT JOIN (
                        SELECT ar.txn_reference, ar.action_status
                        FROM approval_requests ar
                        INNER JOIN (
                            SELECT txn_reference, MAX(id) AS max_id
                            FROM approval_requests
                            GROUP BY txn_reference
                        ) x
                        ON x.txn_reference = ar.txn_reference
                        AND x.max_id = ar.id
                    ) ar_last
                        ON ar_last.txn_reference = a.wo_number

                    WHERE 
                        a.wo_type = %s 
                    AND
                        a.status = %s 
                    AND 
                        a.org_code = %s
                    {bu_filter}
                    {wr_filter}

                    -- ✅ My Work Orders filter (requester OR planner)
                    AND (
                        %s = '0'
                        OR b.email_address = %s
                        OR wotp.planner = %s
                    )

                    GROUP BY 
                        a.wo_number, a.wr_id, b.wr_code, a.wo_code, a.wo_type, a.wo_description,
                        a.job_start_date, a.job_end_date, a.status, a.business_unit,
                        bu.description,
                        e.description, e.code, a.created_datetime, a.due_date, a.revenue,
                        a.actual_total_cost, a.gross_profit, a.cost_type_used,
                        d.firstname, d.lastname, g.firstname, g.lastname,
                        a.location, a.project_name, a.project_description, a.project_gid,
                        a.org_code,
                        b.firstname, b.middlename, b.lastname, b.email_address,
                        b.project_location, b.proposal_deadline, b.job_start_date, b.job_end_date,
                        b.project_desc, b.project_details, c.description,
                        h.service_id, s.description,
                        i.total_cost, i.total_cost_low, i.total_cost_avg,
                        wotp.planner,
                        wor.revenue,
                        ar_last.txn_reference, ar_last.action_status

                    ORDER BY 
                        a.created_datetime DESC
                    LIMIT %s OFFSET %s
                """

                bu_filter = ""
                extra_params = []
                if business_unit != "":
                    bu_filter = " AND a.business_unit = %s "
                    extra_params.append(business_unit)

                wr_filter = ""
                if wr_in_sql:
                    wr_filter = f" AND a.wr_id IN {wr_in_sql} "
                    extra_params.extend(wr_in_params)

                sql1 = sql1.format(bu_filter=bu_filter, wr_filter=wr_filter)
                data1 = (wo_type, status, org_code, *extra_params, my_only, email, email, limit, offset)

            else:
                sql1 = """
                    SELECT 
                        a.wo_number AS wo_number,
                        a.wo_code AS wo_code, 
                        a.wr_id AS wr_id, 
                        b.wr_code AS wr_code, 
                        a.wo_type AS wo_type, 
                        a.wo_description AS wo_description, 
                        a.job_start_date AS wo_job_start_date, 
                        a.job_end_date AS wo_job_end_date, 
                        a.status AS wo_status, 
                        a.business_unit AS business_unit, 
                        bu.description AS company,
                        bu.acronym AS company_acronym, 
                        e.description AS wo_priority_level, 
                        e.code AS wo_priority_level_code, 
                        a.created_datetime AS wo_created_datetime, 
                        a.due_date AS wo_due_date, 

                        -- ✅ revenue from wo_revenues instead of work_orders.revenue
                        COALESCE(wor.revenue, 0) AS revenue,

                        a.actual_total_cost AS actual_total_cost, 
                        a.gross_profit AS gross_profit, 
                        a.cost_type_used AS cost_type_used, 

                        CONCAT(d.firstname, ' ', d.lastname) AS wo_planner, 
                        CONCAT(LEFT(g.firstname,1), ' ', g.lastname) AS initiator, 

                        -- ✅ planner email/login from work_order_team
                        wotp.planner AS wo_planner_code,

                        a.location AS wo_location, 
                        a.project_name AS project_name, 
                        a.project_description AS project_description, 
                        a.project_gid AS wo_project_gid, 
                        a.task_gid AS task_gid, 
                        a.org_code AS org_code, 

                        b.firstname AS firstname,
                        b.middlename AS middlename,
                        b.lastname AS lastname,
                        b.email_address AS email_address,
                        b.project_location AS project_location,
                        DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        b.project_desc AS project_desc,
                        b.project_details AS project_details,

                        c.description AS customer_type, 
                        h.service_id AS service_id,
                        s.description AS scope,

                        GROUP_CONCAT(
                            DISTINCT sd.description
                            ORDER BY sd.description
                            SEPARATOR ', '
                        ) AS sub_scope,

                        i.total_cost AS total_cost,
                        i.total_cost_low AS total_cost_low,
                        i.total_cost_avg AS total_cost_avg,

                        COUNT(DISTINCT f.id) AS unread_count,

                        ar_last.txn_reference AS approval_txn_reference,
                        ar_last.action_status AS approval_action_status

                    FROM 
                        work_orders a 
                    LEFT JOIN
                        work_requests b 
                            ON a.wr_id = b.wr_id
                    LEFT JOIN 
                        customer_types c  
                            ON b.customer_type = c.code
                    LEFT JOIN 
                        app_users d 
                            ON a.planner = d.user  
                    LEFT JOIN 
                        priority_levels e 
                            ON a.priority_level = e.code 
                    LEFT JOIN 
                        app_chatbox f 
                            ON b.project_gid = f.project_gid AND f.read_datetime IS NULL 
                    LEFT JOIN 
                        app_users g 
                            ON b.email_address = g.user 

                    LEFT JOIN 
                        requested_services h
                            ON a.wr_id = h.wr_id 
                    LEFT JOIN
                        services s
                            ON h.service_id = s.service_id
                    LEFT JOIN
                        service_details sd
                            ON h.detail_id = sd.detail_id
                    LEFT JOIN 
                        wo_cost_estimates i
                            ON a.wo_number = i.wo_number 
                    LEFT JOIN
                        business_units bu
                            ON a.business_unit = bu.code

                    -- ✅ planner derived table (1 row per wr_id)
                    LEFT JOIN (
                        SELECT 
                            wr_id,
                            MAX(user) AS planner
                        FROM work_order_team
                        WHERE role = 'planner'
                        GROUP BY wr_id
                    ) wotp
                        ON wotp.wr_id = a.wr_id

                    -- ✅ revenue derived table: SUM(amount) per wo_number
                    LEFT JOIN (
                        SELECT
                            wo_number,
                            SUM(amount) AS revenue
                        FROM wo_revenues
                        GROUP BY wo_number
                    ) wor
                        ON wor.wo_number = a.wo_number

                    LEFT JOIN (
                        SELECT ar.txn_reference, ar.action_status
                        FROM approval_requests ar
                        INNER JOIN (
                            SELECT txn_reference, MAX(id) AS max_id
                            FROM approval_requests
                            GROUP BY txn_reference
                        ) x
                        ON x.txn_reference = ar.txn_reference
                        AND x.max_id = ar.id
                    ) ar_last
                        ON ar_last.txn_reference = a.wo_number

                    WHERE 
                        a.wo_type = %s 
                    AND
                        a.org_code = %s
                    {extra_filter}
                    {wr_filter}

                    -- ✅ My Work Orders filter (requester OR planner)
                    AND (
                        %s = '0'
                        OR b.email_address = %s
                        OR wotp.planner = %s
                    )

                    GROUP BY 
                        a.wo_number, a.wr_id, b.wr_code, a.wo_code, a.wo_type, a.wo_description,
                        a.job_start_date, a.job_end_date, a.status, a.business_unit,
                        bu.description,
                        e.description, e.code, a.created_datetime, a.due_date, a.revenue,
                        a.actual_total_cost, a.gross_profit, a.cost_type_used,
                        d.firstname, d.lastname, g.firstname, g.lastname,
                        a.location, a.project_name, a.project_description, a.project_gid,
                        a.org_code,
                        b.firstname, b.middlename, b.lastname, b.email_address,
                        b.project_location, b.proposal_deadline, b.job_start_date, b.job_end_date,
                        b.project_desc, b.project_details, c.description,
                        h.service_id, s.description,
                        i.total_cost, i.total_cost_low, i.total_cost_avg,
                        wotp.planner,
                        wor.revenue,
                        ar_last.txn_reference, ar_last.action_status

                    ORDER BY 
                        a.created_datetime DESC
                    LIMIT %s OFFSET %s
                """

                extra_filter = ""
                extra_params = []

                if business_unit != "":
                    extra_filter += " AND a.business_unit = %s "
                    extra_params.append(business_unit)

                if wo_status_filter != "":
                    extra_filter += " AND a.status = %s "
                    extra_params.append(wo_status_filter)

                wr_filter = ""
                if wr_in_sql:
                    wr_filter = f" AND a.wr_id IN {wr_in_sql} "
                    extra_params.extend(wr_in_params)

                sql1 = sql1.format(extra_filter=extra_filter, wr_filter=wr_filter)
                data1 = (wo_type, org_code, *extra_params, my_only, email, email, limit, offset)

            cur.execute(sql1, data1)
            result = cur.fetchall()

            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

            if result:
                return jsonify({
                    "message": "Work Orders retrieved successfully",
                    "total": total,
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work orders found",
                    "total": total,
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work orders",
                "error": str(e)
            }), 500


    #--- get work order info ----#
    @app.route('/getworkorderinfo', methods=['GET'])
    def getworkorderinfo():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No Work Order Number field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """
                    SELECT 
                        a.wo_number AS wo_number,
                        a.wo_code AS wo_code, 
                        a.wo_description AS wo_description, 
                        DATE_FORMAT(a.created_datetime, '%%M %%d, %%Y') AS wo_created_datetime, 
                        DATE_FORMAT(a.due_date, '%%M %%d, %%Y') AS wo_due_date, 
                        DATE_FORMAT(a.job_start_date, '%%M %%d, %%Y') AS wo_job_start_date, 
                        DATE_FORMAT(a.job_end_date, '%%M %%d, %%Y') AS wo_job_end_date, 
                        a.status AS wo_status, 
                        a.proposal_status AS proposal_status,
                        a.business_unit AS business_unit_code,
                        g.description AS business_unit, 
                        e.description AS wo_priority_level, 
                        e.code AS wo_priority_level_code, 
                        a.created_datetime AS wo_created_datetime, 
                        a.revenue AS revenue, 
                        a.actual_total_cost AS actual_total_cost, 
                        a.gross_profit AS gross_profit, 
                        a.cost_type_used AS cost_type_used, 
                        CONCAT(f.firstname, ' ', f.lastname) AS requested_by, 
                        CONCAT(d.firstname, ' ', d.lastname) AS wo_planner, 
                        d.user AS wo_planner_code, 
                        a.location As wo_location, 
                        a.project_name AS project_name, 
                        a.project_description AS project_description, 
                        a.project_gid AS wo_project_gid, 
                        a.wr_id AS wr_id, 
                        rs_first.service_id AS service_id,
                        a.org_code AS org_code, 
                        a.ecm_sync AS ecm_sync, 
                        DATE_FORMAT(a.ecm_sync_datetime, '%%M %%d, %%Y %%h:%%i %%p') AS ecm_sync_datetime, 
                        b.firstname AS firstname,
                        b.middlename AS middlename,
                        b.lastname AS lastname,
                        b.email_address AS email_address,
                        b.project_location AS project_location,
                        DATE_FORMAT(b.proposal_deadline, '%%M %%d, %%Y') AS proposal_deadline,
                        DATE_FORMAT(b.job_start_date, '%%M %%d, %%Y') AS job_start_date,
                        DATE_FORMAT(b.job_end_date, '%%M %%d, %%Y') AS job_end_date,
                        b.project_desc AS project_desc,
                        b.project_details AS project_details,
                        c.description AS customer_type 
                    FROM 
                        work_orders a 
                    LEFT JOIN
                        work_requests b 
                    ON 
                        a.wr_id = b.wr_id 
                    LEFT JOIN (
                        SELECT 
                            wr_id,
                            org_code,
                            MIN(service_id) AS service_id
                        FROM requested_services
                        GROUP BY wr_id, org_code
                    ) rs_first
                    ON a.wr_id = rs_first.wr_id
                    AND a.org_code = rs_first.org_code
                    LEFT JOIN 
                        customer_types c  
                    ON 
                        b.customer_type = c.code
                    LEFT JOIN 
                        app_users f 
                    ON
                        a.requested_by = f.user 
                    LEFT JOIN 
                        priority_levels e 
                    ON 
                        a.priority_level = e.code 
                    LEFT JOIN
                        business_units g 
                    ON
                        a.business_unit = g.code 
                    LEFT JOIN 
                        work_order_team h 
                    ON 
                        a.wr_id = h.wr_id AND h.role = %s 
                    LEFT JOIN 
                        app_users d 
                    ON 
                        h.user = d.user  
                    WHERE 
                        a.wo_number = %s 
                    AND 
                        a.org_code = %s 
                    ORDER BY 
                        a.created_datetime DESC
                    """

            data1 = ("planner", wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()

            # Add logic to fetch and consolidate smart_summary
            if result:
                sql2 = """
                    SELECT GROUP_CONCAT(smart_summary SEPARATOR '\n\n') AS smart_summary
                    FROM wo_attachments
                    WHERE wo_number = %s AND smart_summary IS NOT NULL AND TRIM(smart_summary) != ''
                """
                cur.execute(sql2, (wo_number,))
                summary_row = cur.fetchone()
                smart_summary = summary_row['smart_summary'] if summary_row else None

                result[0]['smart_summary'] = smart_summary or ''  # Inject into first (and only) record

                app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

                return jsonify({
                    "message": "Work Order Info retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No more info found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order",
                "error": str(e)
            }), 500


    #--- get work order row ----#
    @app.route('/getworkorderrow', methods=['GET'])
    def getworkorderrow():
        if 'wo_code' in request.args:
            wo_code = request.args['wo_code']
        else:
            return "Error: No Work Order Code field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """
                SELECT wo_code FROM work_orders WHERE wo_code = %s AND org_code = %s 
                """

            data1 = (wo_code, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchone()

            if result:
                app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

                return jsonify({
                    "message": "Work Order Info retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No work order found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve work order",
                "error": str(e)
            }), 500
        

    #--- get all standalone designs ----#
    @app.route('/getstandalones', methods=['GET'])
    def getstandalones():

        if 'status' in request.args:
            status = request.args['status']
        else:
            return "Error: No Status field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """
                    SELECT 
                        a.sa_number AS sa_number,
                        a.sa_description AS sa_description, 
                        a.status AS sa_status, 
                        a.created_datetime AS sa_created_datetime, 
                        b.name AS sa_planner, 
                        b.code AS sa_planner_code, 
                        a.project_name AS project_name, 
                        a.project_description AS project_description, 
                        a.project_gid AS sa_project_gid, 
                        a.org_code AS org_code 
                    FROM 
                        standalone_designs a 
                    LEFT JOIN 
                        planners b 
                    ON 
                        a.planner = b.code 
                    WHERE 
                        a.status = %s AND a.org_code = %s 
                    ORDER BY 
                        a.created_datetime DESC
                    """

            data1 = (status, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are work requests
            if result:
                return jsonify({
                    "message": "Standalone Designs retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No standalone designs found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve standalone designs",
                "error": str(e)
            }), 500
            

    #--- get all physical compatible units ----#
    @app.route('/getphysicalcus', methods=['GET'])
    def getphysical_cus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.org_code AS org_code, b.category AS category_code, b.title AS category_title FROM physical_compatible_units a LEFT JOIN physical_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500


    #--- get all human compatible units ----#
    @app.route('/gethumancus', methods=['GET'])
    def gethuman_cus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.org_code AS org_code, b.category AS category_code, b.title AS category_title FROM human_compatible_units a LEFT JOIN human_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500
            

    #--- get all equipment compatible units ----#
    @app.route('/getequipmentcus', methods=['GET'])
    def getequipment_cus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.org_code AS org_code, b.category AS category_code, b.title AS category_title FROM physical_equip_compatible_units a LEFT JOIN equip_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title"""
            data1 = (1, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500
            

    #--- get all selected/saved physical compatible units ----#
    @app.route('/getselectedcus', methods=['GET'])
    def getselected_cus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.category AS category_code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM wo_compatible_units a LEFT JOIN physical_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
                
            data1 = (wo_number, task_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500


    #--- get all selected/saved physical compatible units for standalone ----#
    @app.route('/getselectedcus2', methods=['GET'])
    def getselected_cus2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM sa_compatible_units a LEFT JOIN physical_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
                
            data1 = (wo_number, task_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500
            

    #--- get all selected/saved human compatible units ----#
    @app.route('/getselectedhumancus', methods=['GET'])
    def getselected_humancus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.category AS category_code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM wo_human_compatible_units a LEFT JOIN human_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
            data1 = (wo_number, task_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500


    #--- get all selected/saved human compatible units for standalone ----#
    @app.route('/getselectedhumancus2', methods=['GET'])
    def getselected_humancus2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM sa_human_compatible_units a LEFT JOIN human_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
            data1 = (wo_number, task_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500
            

    #--- get all selected/saved equipment compatible units ----#
    @app.route('/getselectedequipcus', methods=['GET'])
    def getselected_equipcus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.category AS category_code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM wo_equip_compatible_units a LEFT JOIN physical_equip_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
            data1 = (wo_number, task_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500


    #--- get all selected/saved equipment compatible units ----#
    @app.route('/getselectedequipcus2', methods=['GET'])
    def getselected_equipcus2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.wo_number AS wo_number, a.task_number AS task_number, b.code AS code, b.title AS title, b.description AS description, b.type AS type, a.quantity AS quantity, a.org_code AS org_code FROM sa_equip_compatible_units a LEFT JOIN physical_equip_compatible_units b ON a.cu_code = b.code WHERE a.wo_number = %s AND a.task_number = %s AND a.org_code = %s ORDER BY title"""
            data1 = (wo_number, task_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Compatible Units retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No compatible units found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve compatible units",
                "error": str(e)
            }), 500


    #--- get all materials of a compatible unit ----#
    @app.route('/getcumaterials', methods=['GET'])
    def getcumaterials():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'cu_code' in request.args:
            cu_code = request.args['cu_code']
        else:
            return "Error: No CU Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.quantity AS default_qty, a.unit_of_measure AS uom, b.item_code AS item_code, b.description AS item_description, b.unit_cost AS unit_cost, b.unit_cost_low AS unit_cost_low, b.unit_cost_avg AS unit_cost_avg, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM physical_cu_items a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.status = %s AND a.org_code = %s AND a.cu_code = %s ORDER BY item_description"""
            data1 = (1, org_code, cu_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU materials",
                "error": str(e)
            }), 500
            

    #--- get all labor items of a compatible unit ----#
    @app.route('/gethumanculabors', methods=['GET'])
    def gethumanculabors():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'cu_code' in request.args:
            cu_code = request.args['cu_code']
        else:
            return "Error: No CU Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.quantity AS default_qty, a.duration AS labor_usage, a.duration AS 'usage', a.unit_of_measure AS uom, b.item_code AS item_code, b.description AS item_description, b.unit_cost AS unit_cost, b.unit_cost_low AS unit_cost_low, b.unit_cost_avg AS unit_cost_avg,b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM human_cu_items a LEFT JOIN human_items b ON a.item_code = b.item_code WHERE a.status = %s AND a.org_code = %s AND a.cu_code = %s ORDER BY item_description"""
            data1 = (1, org_code, cu_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU labor items",
                "error": str(e)
            }), 500


    #--- get all equipment items of a physical compatible unit ----#
    @app.route('/getequipmentcuitems', methods=['GET'])
    def getequipmentcuitems():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'cu_code' in request.args:
            cu_code = request.args['cu_code']
        else:
            return "Error: No CU Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.quantity AS default_qty, a.equip_usage AS equip_usage, a.equip_usage AS 'usage', a.unit_of_measure AS uom, b.item_code AS item_code, b.description AS item_description, b.unit_cost AS unit_cost, b.unit_cost_low AS unit_cost_low, b.unit_cost_avg AS unit_cost_avg,b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM physical_equip_cu_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code WHERE a.status = %s AND a.org_code = %s AND a.cu_code = %s ORDER BY item_description"""
            data1 = (1, org_code, cu_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU Equipment items",
                "error": str(e)
            }), 500
            

    #--- get all saved materials of a physical compatible units ----#
    @app.route('/getselectedcumaterials', methods=['GET'])
    def getselectedcumaterials():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
        
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_items a LEFT JOIN physical_items b ON a.item_code = b.item_code LEFT JOIN physical_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU materials",
                "error": str(e)
            }), 500


    #--- get all saved materials of a physical compatible units for standalone ----#
    @app.route('/getselectedcumaterials2', methods=['GET'])
    def getselectedcumaterials2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
        
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_items a LEFT JOIN physical_items b ON a.item_code = b.item_code LEFT JOIN physical_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU materials",
                "error": str(e)
            }), 500
            

    #--- get all saved labor items of a human compatible units ----#
    @app.route('/getselectedhumanculabors', methods=['GET'])
    def getselectedhumanculabors():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
        
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.duration AS labor_usage, a.duration AS 'usage', c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_human_items a LEFT JOIN human_items b ON a.item_code = b.item_code LEFT JOIN human_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU labor items",
                "error": str(e)
            }), 500
            

    #--- get all saved labor items of a human compatible units for standalone ----#
    @app.route('/getselectedhumanculabors2', methods=['GET'])
    def getselectedhumanculabors2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
        
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_human_items a LEFT JOIN human_items b ON a.item_code = b.item_code LEFT JOIN human_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU labor items",
                "error": str(e)
            }), 500
            

    #--- get all saved labor items of a equipment compatible units ----#
    @app.route('/getselectedequipcuitems', methods=['GET'])
    def getselectedequipcuitems():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
        
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, a.equip_usage AS equip_usage, a.equip_usage AS 'usage', c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_equip_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code LEFT JOIN physical_equip_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU equipment items",
                "error": str(e)
            }), 500


    #--- get all saved labor items of a equipment compatible units for standalone ----#
    @app.route('/getselectedequipcuitems2', methods=['GET'])
    def getselectedequipcuitems2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
        
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.cu_code AS cu_code, a.quantity AS quantity, c.quantity AS default_qty, a.uom AS uom, b.item_code AS item_code, b.description AS item_description, a.unit_cost AS unit_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_equip_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code LEFT JOIN physical_equip_cu_items c ON a.cu_code = c.cu_code AND a.item_code = c.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY item_description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU equipment items",
                "error": str(e)
            }), 500
            

    #--- get all materials ----#
    @app.route('/getmaterials', methods=['GET'])
    def getmaterials():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.brand AS brand, a.supplier AS supplier, a.source AS source, a.year AS year, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_items a LEFT JOIN physical_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s ORDER BY description LIMIT %s, %s"""
            
            data1 = (1, org_code, offset, limit)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500


    # --- get materials by partial description --- #
    @app.route('/getmaterialsdesc', methods=['GET'])
    def getmaterialsdesc():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'description' in request.args:
            description = '%' + request.args['description'].strip() + '%'
        else:
            return "Error: No Description field provided. Please specify it."    
            
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_items a LEFT JOIN physical_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s AND a.description LIKE %s ORDER BY description"""
            
            data1 = (1, org_code, description)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500
        
    
    #--- get all materials per category ----#
    @app.route('/getmaterialspercategory', methods=['GET'])
    def getmaterialspercategory():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        if 'category' in request.args:
            category = request.args['category']
        else:
            return "Error: No Category Code field provided. Please specify it."
        
        '''
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        '''
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT item_code, description, unit_cost, acquisition_type, unit_of_measure AS uom, category, org_code FROM physical_items WHERE status = %s AND org_code = %s AND category = %s ORDER BY description"""
            data1 = (1, org_code, category)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500


    #--- get all labor per category ----#
    @app.route('/getlaborpercategory', methods=['GET'])
    def getlaborpercategory():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        if 'category' in request.args:
            category = request.args['category']
        else:
            return "Error: No Category Code field provided. Please specify it."
        
        '''
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        '''
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT item_code, description, unit_cost, acquisition_type, unit_of_measure AS uom, category, org_code FROM human_items WHERE status = %s AND org_code = %s AND category = %s ORDER BY description"""
            data1 = (1, org_code, category)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve labor items",
                "error": str(e)
            }), 500
            
    
    #--- get all equipment per category ----#
    @app.route('/getequipmentpercategory', methods=['GET'])
    def getequipmentpercategory():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        if 'category' in request.args:
            category = request.args['category']
        else:
            return "Error: No Category Code field provided. Please specify it."
        
        '''
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        '''
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT item_code, description, unit_cost, acquisition_type, unit_of_measure AS uom, category, org_code FROM physical_equip_items WHERE status = %s AND org_code = %s AND category = %s ORDER BY description"""
            data1 = (1, org_code, category)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve equipment items",
                "error": str(e)
            }), 500
    
    
    #--- get all labor items ----#
    @app.route('/getlabors', methods=['GET'])
    def getlabors():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM human_items a LEFT JOIN human_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s ORDER BY description LIMIT %s, %s"""

            data1 = (1, org_code, offset, limit)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve labor items",
                "error": str(e)
            }), 500
    

    #--- get labor items by description ----#
    @app.route('/getlaborsdesc', methods=['GET'])
    def getlaborsdesc():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'description' in request.args:
            description = '%' + request.args['description'].strip() + '%'
        else:
            return "Error: No Description field provided. Please specify it."    
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM human_items a LEFT JOIN human_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s AND a.description LIKE %s ORDER BY description"""

            data1 = (1, org_code, description)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve labor items",
                "error": str(e)
            }), 500


    #--- get equipment items by description ----#
    @app.route('/getequipmentitemsdesc', methods=['GET'])
    def getequipmentitemsdesc():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'description' in request.args:
            description = '%' + request.args['description'].strip() + '%'
        else:
            return "Error: No Description field provided. Please specify it."    
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_equip_items a LEFT JOIN equip_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s AND a.description LIKE %s ORDER BY description"""
            
            data1 = (1, org_code, description)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve equipment items",
                "error": str(e)
            }), 500
        
    
    #--- get all equipment items ----#
    @app.route('/getequipmentitems', methods=['GET'])
    def getequipmentitems():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, a.description AS description, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.acquisition_type AS acquisition_type, a.unit_of_measure AS uom, a.org_code AS org_code, a.category AS category, b.description AS category_desc FROM physical_equip_items a LEFT JOIN equip_item_categories b ON a.category = b.id WHERE a.status = %s AND a.org_code = %s ORDER BY description LIMIT %s, %s"""
            
            data1 = (1, org_code, offset, limit)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve equipment items",
                "error": str(e)
            }), 500
        

    #--- get all material CUs ----#
    @app.route('/getmaterialcus', methods=['GET'])
    def getmaterialcus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.category AS category, b.title AS category_title  FROM physical_compatible_units a LEFT JOIN physical_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title LIMIT %s, %s"""
            
            data1 = (1, org_code, offset, limit)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CUs retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CUs found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CUs",
                "error": str(e)
            }), 500 


    #--- get all labor CUs ----#
    @app.route('/getlaborcus', methods=['GET'])
    def getlaborcus():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'offset' in request.args:
            offset = int(request.args['offset'])
        else:
            return "Error: No Pagination Offset field provided. Please specify it."    
            
        if 'limit' in request.args:
            limit = int(request.args['limit'])
        else:
            return "Error: No Pagination Limit field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.code AS code, a.title AS title, a.description AS description, a.quantity AS quantity, a.type AS type, a.category AS category, b.title AS category_title  FROM human_compatible_units a LEFT JOIN human_cu_categories b ON a.category = b.category WHERE a.status = %s AND a.org_code = %s ORDER BY title LIMIT %s, %s"""
            
            data1 = (1, org_code, offset, limit)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CUs retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CUs found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CUs",
                "error": str(e)
            }), 500 


    #--- get all saved custom materials ----#
    @app.route('/getselectedcustommaterials', methods=['GET'])
    def getselectedcustommaterials():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.unit_cost_low AS unit_cost_low, a.unit_cost_avg AS unit_cost_avg, a.total_cost AS total_cost, a.total_cost_low AS total_cost_low, a.total_cost_avg AS total_cost_avg, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_custom_items a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500


    #--- get all saved custom materials for standalone ----#
    @app.route('/getselectedcustommaterials2', methods=['GET'])
    def getselectedcustommaterials2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_custom_items a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500
            

    #--- get all saved custom labor items ----#
    @app.route('/getselectedhumancustomlabors', methods=['GET'])
    def getselectedhumancustomlabors():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.duration AS labor_usage, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_human_custom_items a LEFT JOIN human_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve labor items",
                "error": str(e)
            }), 500        
            

    #--- get all saved custom labor items ----#
    @app.route('/getselectedhumancustomlabors2', methods=['GET'])
    def getselectedhumancustomlabors2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_human_custom_items a LEFT JOIN human_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Labor Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Labor Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve labor items",
                "error": str(e)
            }), 500        


    #--- get all saved custom equipment items ----#
    @app.route('/getselectedequipcustomitems', methods=['GET'])
    def getselectedequipcustomitems():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.equip_usage AS equip_usage, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM wo_task_physical_equip_custom_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve equipment items",
                "error": str(e)
            }), 500
            

    #--- get all saved custom equipment items for standalone ----#
    @app.route('/getselectedequipcustomitems2', methods=['GET'])
    def getselectedequipcustomitems2():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'task_number' in request.args:
            task_number = request.args['task_number']
        else:
            return "Error: No Task Number field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.item_code AS item_code, b.description AS description, a.quantity AS quantity, a.uom AS uom, a.unit_cost AS unit_cost, a.total_cost AS total_cost, b.acquisition_type AS acquisition_type, a.org_code AS org_code FROM sa_task_physical_equip_custom_items a LEFT JOIN physical_equip_items b ON a.item_code = b.item_code WHERE a.org_code = %s AND a.wo_number = %s AND a.task_number = %s ORDER BY description"""
            data1 = (org_code, wo_number, task_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Equipment Items retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Equipment Items found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve equipment items",
                "error": str(e)
            }), 500
            
    
    #--- get bill of materials ----        
    @app.route('/getbommaterials', methods=['GET'])
    def get_bom_materials():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            curs = conn.cursor()
            
            # SQL Query to retrieve compatible units and custom resources
            query = """
            SELECT 
                'Compatible Unit' AS type, 
                c.title AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                a.unit_cost_low AS unit_cost_low, 
                a.unit_cost_avg AS unit_cost_avg, 
                (a.quantity * a.unit_cost) AS total_cost, 
                (a.quantity * a.unit_cost_low) AS total_cost_low, 
                (a.quantity * a.unit_cost_avg) AS total_cost_avg, 
                a.uom AS uom 
            FROM 
                wo_task_physical_items a 
            LEFT JOIN 
                physical_items b 
            ON 
                a.item_code = b.item_code 
            LEFT JOIN 
                physical_compatible_units c 
            ON 
                a.cu_code = c.code 
            WHERE 
                a.wo_number = %s 

            UNION ALL

            SELECT 
                'Custom Resource' AS type,
                'Custom' AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                a.unit_cost_low AS unit_cost_low, 
                a.unit_cost_avg AS unit_cost_avg, 
                (a.quantity * a.unit_cost) AS total_cost, 
                (a.quantity * a.unit_cost_low) AS total_cost_low, 
                (a.quantity * a.unit_cost_avg) AS total_cost_avg, 
                a.uom AS uom 
            FROM 
                wo_task_physical_custom_items a 
            LEFT JOIN
                physical_items b 
            ON
                a.item_code = b.item_code 
            WHERE 
                a.wo_number = %s
            """
            
            # Execute query
            curs.execute(query, (wo_number, wo_number))
            materials = curs.fetchall()

            # Group materials by type (Compatible Unit or Custom Resource)
            grouped_materials = {
                "Compatible Unit": {},
                "Custom Resource": {}
            }

            for material in materials:
                material_type = material['type']
                cu_title = material['cu_title']
                item_data = {
                    'item_code': material['item_code'],
                    'description': material['description'],
                    'quantity': material['quantity'],
                    'unit_cost': material['unit_cost'],
                    'unit_cost_low': material['unit_cost_low'],
                    'unit_cost_avg': material['unit_cost_avg'],
                    'total_cost': material['total_cost'],
                    'total_cost_low': material['total_cost_low'],
                    'total_cost_avg': material['total_cost_avg'],
                    'uom': material['uom']
                }

                # Group by type, then by cu_title
                if cu_title not in grouped_materials[material_type]:
                    grouped_materials[material_type][cu_title] = []
                grouped_materials[material_type][cu_title].append(item_data)

            # Prepare the response
            result = {
                'wo_number': wo_number,
                'materials': []
            }

            # Add the grouped data to the response
            for material_type, cu_data in grouped_materials.items():
                type_group = {'type': material_type, 'cu_groups': []}
                for cu_title, items in cu_data.items():
                    type_group['cu_groups'].append({
                        'cu_title': cu_title,
                        'items': items
                    })
                result['materials'].append(type_group)

            # Check if there are records
            if result['materials']:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500


    #--- get bill of materials for standalone ----        
    @app.route('/getbommaterials2', methods=['GET'])
    def get_bom_materials2():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            curs = conn.cursor()
            
            # SQL Query to retrieve compatible units and custom resources
            query = """
            SELECT 
                'Compatible Unit' AS type, 
                c.title AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                (a.quantity * a.unit_cost) AS total_cost, 
                a.uom AS uom 
            FROM 
                sa_task_physical_items a 
            LEFT JOIN 
                physical_items b 
            ON 
                a.item_code = b.item_code 
            LEFT JOIN 
                physical_compatible_units c 
            ON 
                a.cu_code = c.code 
            WHERE 
                a.wo_number = %s 

            UNION ALL

            SELECT 
                'Custom Resource' AS type,
                'Custom' AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                (a.quantity * a.unit_cost) AS total_cost, 
                a.uom AS uom 
            FROM 
                sa_task_physical_custom_items a 
            LEFT JOIN
                physical_items b 
            ON
                a.item_code = b.item_code 
            WHERE 
                a.wo_number = %s
            """
            
            # Execute query
            curs.execute(query, (wo_number, wo_number))
            materials = curs.fetchall()

            # Group materials by type (Compatible Unit or Custom Resource)
            grouped_materials = {
                "Compatible Unit": {},
                "Custom Resource": {}
            }

            for material in materials:
                material_type = material['type']
                cu_title = material['cu_title']
                item_data = {
                    'item_code': material['item_code'],
                    'description': material['description'],
                    'quantity': material['quantity'],
                    'unit_cost': material['unit_cost'],
                    'total_cost': material['total_cost'],
                    'uom': material['uom']
                }

                # Group by type, then by cu_title
                if cu_title not in grouped_materials[material_type]:
                    grouped_materials[material_type][cu_title] = []
                grouped_materials[material_type][cu_title].append(item_data)

            # Prepare the response
            result = {
                'wo_number': wo_number,
                'materials': []
            }

            # Add the grouped data to the response
            for material_type, cu_data in grouped_materials.items():
                type_group = {'type': material_type, 'cu_groups': []}
                for cu_title, items in cu_data.items():
                    type_group['cu_groups'].append({
                        'cu_title': cu_title,
                        'items': items
                    })
                result['materials'].append(type_group)

            # Check if there are records
            if result['materials']:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500
            

    #--- get BoM - labor ----        
    @app.route('/getbomlabor', methods=['GET'])
    def get_bom_labor():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            curs = conn.cursor()
            
            # SQL Query to retrieve compatible units and custom resources
            query = """
            SELECT 
                'Compatible Unit' AS type, 
                c.title AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity,
                a.duration AS labor_usage,  
                a.unit_cost AS unit_cost, 
                a.total_cost AS total_cost, 
                a.uom AS uom 
            FROM 
                wo_task_human_items a 
            LEFT JOIN 
                human_items b 
            ON 
                a.item_code = b.item_code 
            LEFT JOIN 
                human_compatible_units c 
            ON 
                a.cu_code = c.code 
            WHERE 
                a.wo_number = %s 

            UNION ALL

            SELECT 
                'Custom Resource' AS type,
                'Custom' AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.duration AS labor_usage, 
                a.unit_cost AS unit_cost, 
                a.total_cost AS total_cost, 
                a.uom AS uom 
            FROM 
                wo_task_human_custom_items a 
            LEFT JOIN
                human_items b 
            ON
                a.item_code = b.item_code 
            WHERE 
                a.wo_number = %s
            """
            
            # Execute query
            curs.execute(query, (wo_number, wo_number))
            materials = curs.fetchall()

            # Group materials by type (Compatible Unit or Custom Resource)
            grouped_materials = {
                "Compatible Unit": {},
                "Custom Resource": {}
            }

            for material in materials:
                material_type = material['type']
                cu_title = material['cu_title']
                item_data = {
                    'item_code': material['item_code'],
                    'description': material['description'],
                    'quantity': material['quantity'],
                    'labor_usage': material['labor_usage'],
                    'unit_cost': material['unit_cost'],
                    'total_cost': material['total_cost'],
                    'uom': material['uom']
                }

                # Group by type, then by cu_title
                if cu_title not in grouped_materials[material_type]:
                    grouped_materials[material_type][cu_title] = []
                grouped_materials[material_type][cu_title].append(item_data)

            # Prepare the response
            result = {
                'wo_number': wo_number,
                'materials': []
            }

            # Add the grouped data to the response
            for material_type, cu_data in grouped_materials.items():
                type_group = {'type': material_type, 'cu_groups': []}
                for cu_title, items in cu_data.items():
                    type_group['cu_groups'].append({
                        'cu_title': cu_title,
                        'items': items
                    })
                result['materials'].append(type_group)

            # Check if there are records
            if result['materials']:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500


    #--- get BoM - labor for standalone ----        
    @app.route('/getbomlabor2', methods=['GET'])
    def get_bom_labor2():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            curs = conn.cursor()
            
            # SQL Query to retrieve compatible units and custom resources
            query = """
            SELECT 
                'Compatible Unit' AS type, 
                c.title AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                (a.quantity * a.unit_cost) AS total_cost, 
                a.uom AS uom 
            FROM 
                sa_task_human_items a 
            LEFT JOIN 
                human_items b 
            ON 
                a.item_code = b.item_code 
            LEFT JOIN 
                human_compatible_units c 
            ON 
                a.cu_code = c.code 
            WHERE 
                a.wo_number = %s 

            UNION ALL

            SELECT 
                'Custom Resource' AS type,
                'Custom' AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                (a.quantity * a.unit_cost) AS total_cost, 
                a.uom AS uom 
            FROM 
                sa_task_human_custom_items a 
            LEFT JOIN
                human_items b 
            ON
                a.item_code = b.item_code 
            WHERE 
                a.wo_number = %s
            """
            
            # Execute query
            curs.execute(query, (wo_number, wo_number))
            materials = curs.fetchall()

            # Group materials by type (Compatible Unit or Custom Resource)
            grouped_materials = {
                "Compatible Unit": {},
                "Custom Resource": {}
            }

            for material in materials:
                material_type = material['type']
                cu_title = material['cu_title']
                item_data = {
                    'item_code': material['item_code'],
                    'description': material['description'],
                    'quantity': material['quantity'],
                    'unit_cost': material['unit_cost'],
                    'total_cost': material['total_cost'],
                    'uom': material['uom']
                }

                # Group by type, then by cu_title
                if cu_title not in grouped_materials[material_type]:
                    grouped_materials[material_type][cu_title] = []
                grouped_materials[material_type][cu_title].append(item_data)

            # Prepare the response
            result = {
                'wo_number': wo_number,
                'materials': []
            }

            # Add the grouped data to the response
            for material_type, cu_data in grouped_materials.items():
                type_group = {'type': material_type, 'cu_groups': []}
                for cu_title, items in cu_data.items():
                    type_group['cu_groups'].append({
                        'cu_title': cu_title,
                        'items': items
                    })
                result['materials'].append(type_group)

            # Check if there are records
            if result['materials']:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500
            

    #--- get BoM - Equipment ----      
    @app.route('/getbomequipment', methods=['GET'])
    def get_bom_equipment():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            curs = conn.cursor()
            
            # SQL Query to retrieve compatible units and custom resources
            query = """
            SELECT 
                'Compatible Unit' AS type, 
                c.title AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.equip_usage AS equip_usage, 
                a.unit_cost AS unit_cost, 
                a.total_cost AS total_cost, 
                a.uom AS uom 
            FROM 
                wo_task_physical_equip_items a 
            LEFT JOIN 
                physical_equip_items b 
            ON 
                a.item_code = b.item_code 
            LEFT JOIN 
                physical_equip_compatible_units c 
            ON 
                a.cu_code = c.code 
            WHERE 
                a.wo_number = %s 

            UNION ALL

            SELECT 
                'Custom Resource' AS type,
                'Custom' AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.equip_usage AS equip_usage, 
                a.unit_cost AS unit_cost, 
                a.total_cost AS total_cost, 
                a.uom AS uom 
            FROM 
                wo_task_physical_equip_custom_items a 
            LEFT JOIN
                physical_equip_items b 
            ON
                a.item_code = b.item_code 
            WHERE 
                a.wo_number = %s
            """
            
            # Execute query
            curs.execute(query, (wo_number, wo_number))
            materials = curs.fetchall()

            # Group materials by type (Compatible Unit or Custom Resource)
            grouped_materials = {
                "Compatible Unit": {},
                "Custom Resource": {}
            }

            for material in materials:
                material_type = material['type']
                cu_title = material['cu_title']
                item_data = {
                    'item_code': material['item_code'],
                    'description': material['description'],
                    'quantity': material['quantity'],
                    'equip_usage': material['equip_usage'],
                    'unit_cost': material['unit_cost'],
                    'total_cost': material['total_cost'],
                    'uom': material['uom']
                }

                # Group by type, then by cu_title
                if cu_title not in grouped_materials[material_type]:
                    grouped_materials[material_type][cu_title] = []
                grouped_materials[material_type][cu_title].append(item_data)

            # Prepare the response
            result = {
                'wo_number': wo_number,
                'materials': []
            }

            # Add the grouped data to the response
            for material_type, cu_data in grouped_materials.items():
                type_group = {'type': material_type, 'cu_groups': []}
                for cu_title, items in cu_data.items():
                    type_group['cu_groups'].append({
                        'cu_title': cu_title,
                        'items': items
                    })
                result['materials'].append(type_group)

            # Check if there are records
            if result['materials']:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500


    #--- get BoM - Equipment for standalone ----        
    @app.route('/getbomequipment2', methods=['GET'])
    def get_bom_equipment2():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            curs = conn.cursor()
            
            # SQL Query to retrieve compatible units and custom resources
            query = """
            SELECT 
                'Compatible Unit' AS type, 
                c.title AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                (a.quantity * a.unit_cost) AS total_cost, 
                a.uom AS uom 
            FROM 
                sa_task_physical_equip_items a 
            LEFT JOIN 
                physical_equip_items b 
            ON 
                a.item_code = b.item_code 
            LEFT JOIN 
                physical_equip_compatible_units c 
            ON 
                a.cu_code = c.code 
            WHERE 
                a.wo_number = %s 

            UNION ALL

            SELECT 
                'Custom Resource' AS type,
                'Custom' AS cu_title, 
                a.item_code AS item_code, 
                b.description AS description, 
                a.quantity AS quantity, 
                a.unit_cost AS unit_cost, 
                (a.quantity * a.unit_cost) AS total_cost, 
                a.uom AS uom 
            FROM 
                sa_task_physical_equip_custom_items a 
            LEFT JOIN
                physical_equip_items b 
            ON
                a.item_code = b.item_code 
            WHERE 
                a.wo_number = %s
            """
            
            # Execute query
            curs.execute(query, (wo_number, wo_number))
            materials = curs.fetchall()

            # Group materials by type (Compatible Unit or Custom Resource)
            grouped_materials = {
                "Compatible Unit": {},
                "Custom Resource": {}
            }

            for material in materials:
                material_type = material['type']
                cu_title = material['cu_title']
                item_data = {
                    'item_code': material['item_code'],
                    'description': material['description'],
                    'quantity': material['quantity'],
                    'unit_cost': material['unit_cost'],
                    'total_cost': material['total_cost'],
                    'uom': material['uom']
                }

                # Group by type, then by cu_title
                if cu_title not in grouped_materials[material_type]:
                    grouped_materials[material_type][cu_title] = []
                grouped_materials[material_type][cu_title].append(item_data)

            # Prepare the response
            result = {
                'wo_number': wo_number,
                'materials': []
            }

            # Add the grouped data to the response
            for material_type, cu_data in grouped_materials.items():
                type_group = {'type': material_type, 'cu_groups': []}
                for cu_title, items in cu_data.items():
                    type_group['cu_groups'].append({
                        'cu_title': cu_title,
                        'items': items
                    })
                result['materials'].append(type_group)

            # Check if there are records
            if result['materials']:
                return jsonify({
                    "message": "Materials retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Materials found",
                    "result": []
                }), 404

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500
            

    #--- get work order cost estimate ----#
    @app.route('/getwocostestimate', methods=['GET'])
    def getwocostestimate():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT * FROM wo_cost_estimates WHERE wo_number = %s AND org_code = %s"""
            
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Cost Estimate retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No cost estimate found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve cost estimate",
                "error": str(e)
            }), 500


    #--- get work order cost estimate for standalone ----#
    @app.route('/getwocostestimate2', methods=['GET'])
    def getwocostestimate2():
        if 'wo_number' in request.args:
            wo_number = int(request.args['wo_number'])
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT * FROM sa_cost_estimates WHERE wo_number = %s AND org_code = %s"""
            
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Cost Estimate retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No cost estimate found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve cost estimate",
                "error": str(e)
            }), 500


    #--- get work orders count ----#
    @app.route('/getworkorderscount', methods=['GET'])
    def getworkorderscount():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)

            sql1 = """
                SELECT status, COUNT(*) AS wo_count 
                FROM work_orders 
                WHERE status IN (
                    'New',
                    'Started',
                    'Approved',
                    'In Progress',
                    'Completed',
                    'On Hold',
                    'Cancelled'
                ) 
                AND wo_type = %s  
                AND org_code = %s 
                GROUP BY status
            """

            data1 = ("FWO", org_code)

            cur.execute(sql1, data1)
            result = cur.fetchall()

            status_counts = {
                "New": 0,
                "Started": 0,
                "Approved": 0,
                "In Progress": 0,
                "Completed": 0,
                "On Hold": 0,
                "Cancelled": 0,
                "open_proposal_count": 0,
            }

            for row in result:
                status = row['status']
                count = row['wo_count']

                if status in status_counts:
                    status_counts[status] = count

            sql2 = """
                SELECT COUNT(*) AS open_proposal_count
                FROM work_orders wo
                INNER JOIN (
                    SELECT
                        wr_id,
                        org_code,
                        MIN(service_id) AS service_id
                    FROM requested_services
                    GROUP BY wr_id, org_code
                ) rs
                    ON wo.wr_id = rs.wr_id
                AND wo.org_code = rs.org_code
                WHERE wo.wo_type = %s
                AND wo.org_code = %s
                AND COALESCE(wo.proposal_status, '') <> 'Awarded'
                AND wo.status NOT IN ('Completed', 'Cancelled')
                AND rs.service_id NOT IN (1, 3)
            """
            ## 1 - PD, 3 - O&M 

            cur.execute(sql2, ("FWO", org_code))
            proposal_row = cur.fetchone()

            if proposal_row:
                status_counts["open_proposal_count"] = (
                    proposal_row["open_proposal_count"] or 0
                )

            return jsonify({
                "message": "Work Orders Count retrieved successfully",
                "result": status_counts
            }), 200

        except Exception as e:
            return jsonify({
                "message": "Failed to count work orders",
                "error": str(e)
            }), 500

        finally:
            try:
                cur.close()
                conn.close()
            except:
                pass


    #--- get work orders count by BUs ----#
    @app.route('/getworkorderscountbybu', methods=['GET'])
    def getworkorderscount_by_bu():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return jsonify({
                "message": "Error: No Organization Code field provided. Please specify it."
            }), 400
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 =  """
                    SELECT business_unit, COUNT(*) AS wo_count 
                    FROM work_orders 
                    WHERE org_code = %s 
                    GROUP BY business_unit
                    """
            data1 = (org_code,)  # Ensure tuple format
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Process the result into a dictionary format
            bu_counts = {row['business_unit']: row['wo_count'] for row in result}

            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Orders Count retrieved successfully",
                    "result": bu_counts
                }), 200
            else:
                return jsonify({
                    "message": "No count found",
                    "result": {}
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to count work orders",
                "error": str(e)
            }), 500
            

    #--- get work orders profit by BUs ----#
    @app.route('/getworkordersprofitbybu', methods=['GET'])
    def getworkordersprofit_by_bu():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return jsonify({
                "message": "Error: No Organization Code field provided. Please specify it."
            }), 400
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 =  """
                    SELECT business_unit, SUM(gross_profit) AS wo_profit 
                    FROM work_orders 
                    WHERE org_code = %s 
                    GROUP BY business_unit
                    """
            data1 = (org_code,)  # Ensure tuple format
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Process the result into a dictionary format
            bu_counts = {row['business_unit']: row['wo_profit'] for row in result}

            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Orders Profit retrieved successfully",
                    "result": bu_counts
                }), 200
            else:
                return jsonify({
                    "message": "No profit found",
                    "result": {}
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to sum profit of work orders",
                "error": str(e)
            }), 500


    #--- get work requests count ----#
    @app.route('/getworkrequestscount', methods=['GET'])
    def getworkrequestscount():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT status, COUNT(*) AS wr_count 
                    FROM work_requests  
                    WHERE status IN ('Queue', 'Team Assigned', 'Accepted', 'Declined', 'On Hold', 'Closed') 
                    AND org_code = %s 
                    GROUP BY status"""
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Process the result to map statuses to the required output format
            status_counts = { "Queue": 0, "Team Assigned": 0, "Accepted": 0, "Declined": 0, "On Hold": 0, "Closed": 0 }
            
            # Map the results to the response format
            for row in result:
                status = row['status']
                count = row['wr_count']
                if status in status_counts:
                    status_counts[status] = count
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Requests Count retrieved successfully",
                    "result": status_counts
                }), 200
            else:
                return jsonify({
                    "message": "No count found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to count work requests",
                "error": str(e)
            }), 500


    #--- get count of work request proposal to due this week ----#
    @app.route('/getwrproposalsduecount', methods=['GET'])
    def getwrproposalsduecount():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT COUNT(*) AS due_this_week FROM work_requests WHERE proposal_deadline BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY) AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY) AND status IN (%s, %s) AND org_code = %s"""
            data1 = ("Queue", "On Review", org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Proposals Count retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No count found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to count proposal",
                "error": str(e)
            }), 500


    #--- get count of work orders to due this week ----#
    @app.route('/getworkordersduecount', methods=['GET'])
    def getworkordersduecount():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT COUNT(*) AS due_this_week FROM work_orders WHERE due_date BETWEEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY) AND DATE_ADD(DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY), INTERVAL 6 DAY) AND status IN (%s, %s, %s, %s) AND wo_type = %s AND org_code = %s"""
            data1 = ("New", "Kickoff", "Executed", "Billed", "FWO", org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Orders Count retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No count found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to count work orders",
                "error": str(e)
            }), 500
        

    #--- get count of overdue work orders ----#
    @app.route('/getworkordersoverduecount', methods=['GET'])
    def getworkordersoverduecount():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT COUNT(*) AS overdue FROM work_orders WHERE due_date < CURDATE() AND status IN (%s, %s) AND wo_type = %s AND org_code = %s"""
            data1 = ("New", "Kickoff", "FWO", org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Orders Count retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No count found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to count work orders",
                "error": str(e)
            }), 500


    #--- get monthly total of all cost estimates ----#
    @app.route('/getsumwocostestimatemonthly', methods=['GET'])
    def getsumwocostestimatemonthly():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 =  """
                    SELECT 
                    DATE_FORMAT(wo.created_datetime, '%%b %%Y') AS month_year,
                    SUM(
                        CASE wo.cost_type_used
                        WHEN 'High' THEN ce.total_cost
                        WHEN 'Low' THEN ce.total_cost_low
                        WHEN 'Average' THEN ce.total_cost_avg
                        ELSE 0
                        END
                    ) AS total_estimated_cost
                    FROM wac.work_orders wo
                    JOIN wac.wo_cost_estimates ce ON wo.wo_number = ce.wo_number
                    WHERE wo.wo_type = %s AND wo.org_code = %s 
                    GROUP BY DATE_FORMAT(wo.created_datetime, '%%Y-%%m')
                    ORDER BY DATE_FORMAT(wo.created_datetime, '%%Y-%%m')
                    """
            data1 = ("FWO", org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Monthly WO Cost Estimates Total retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No total found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to compute monthly cost estimates total",
                "error": str(e)
            }), 500


    #--- get work request requested services count ----#
    @app.route('/getwrrequestedservicescount', methods=['GET'])
    def getwrrequestedservicescount():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 =  """
                    SELECT 
                    s.description AS service_desc,
                    sd.description AS detail_desc,
                    COUNT(DISTINCT rs.wr_id) AS work_request_count
                    FROM wac.requested_services rs LEFT JOIN wac.services s ON rs.service_id = s.service_id LEFT JOIN wac.service_details sd ON rs.detail_id = sd.detail_id WHERE rs.org_code = %s GROUP BY s.description, sd.description ORDER BY s.description, sd.description
                    """
            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "WR Requested Services retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No count found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to count WR requested services",
                "error": str(e)
            }), 500
        

    #--- get work order time-state ----#
    @app.route('/getwotimestate', methods=['GET'])
    def getwotimestate():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."

        #if 'wr_id' in request.args:
        #    wr_id = request.args['wr_id']
        #else:
        #    return "Error: No WR Id field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            
            #sql1 =  """
            #        SELECT txn_type, txn_reference, new_status, changed_on FROM wac.status_changes WHERE (txn_reference = %s AND txn_type = "Work Order") OR (txn_reference = %s AND txn_type = "Work Request") AND org_code = %s 
            #        """
            
            sql1 =  """
                    SELECT txn_type, txn_reference, new_status, changed_on FROM status_changes WHERE (txn_reference = %s AND txn_type = "Work Order")  AND org_code = %s 
                    """
            #data1 = (wo_number, wr_id, org_code)
            data1 = (wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "WO time-state data retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No time-state found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve time-state data",
                "error": str(e)
            }), 500


    #--- get all work orders statuses time-state ----#
    @app.route('/getallwotimestate', methods=['GET'])
    def getallwotimestate():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 =  """
                    SELECT txn_type, txn_reference, new_status, changed_on 
                    FROM wac.status_changes 
                    WHERE org_code = %s 
                    AND new_status != 'Reference'
                    """

            data1 = (org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "WO time-state data retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No time-state found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve time-state data",
                "error": str(e)
            }), 500


    #--- get work requests and work orders for approval ----#
    @app.route('/getwrwoapproval', methods=['GET'])
    def getwrwoapproval():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'acted_user' in request.args:
            acted_user = request.args['acted_user']
        else:
            return "Error: No User field provided. Please specify it."

        if 'role_titles' in request.args:
            role_titles_param = request.args.get("role_titles", "")
            role_titles = role_titles_param.split(",")
        else:
            return "Error: No Role Title field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            if "team lead" in role_titles and "manager" in role_titles:
                sql1 = """SELECT 
                            a.id AS id,
                            a.txn_type AS txn_type,
                            a.txn_reference AS txn_reference,
                            a.description AS description,
                            a.approval_type AS approval_type,
                            a.requested_by AS requested_by,
                            a.requested_datetime AS requested_datetime,
                            a.action_status AS action_status,
                            a.acted_by AS acted_by,
                            a.acted_datetime AS acted_datetime,
                            a.comment AS comment,
                            a.org_code AS org_code,
                            b.wr_id AS wr_id,
                            b.wo_number AS wo_number, 
                            b.wo_code AS wo_code,
                            b.job_end_date AS job_end_date,
                            b.project_name AS project_name,
                            b.project_description AS project_description, 
                            c.service_id AS service_id,
                            s.description AS scope,
                            bu.description AS company,
                            bu.acronym AS company_acronym,
                            GROUP_CONCAT(
                              DISTINCT sd.description
                              ORDER BY sd.description
                              SEPARATOR ', '
                            ) AS sub_scope,
                            b.wo_description AS wo_description
                        FROM approval_requests a
                        LEFT JOIN work_orders b
                            ON a.txn_reference = b.wo_number
                        LEFT JOIN (
                            SELECT rs.wr_id, rs.service_id, rs.detail_id 
                            FROM requested_services rs
                            INNER JOIN (
                                SELECT wr_id, MIN(id) AS first_id
                                FROM requested_services
                                GROUP BY wr_id
                            ) x
                                ON x.wr_id = rs.wr_id
                            AND x.first_id = rs.id
                        ) c
                            ON b.wr_id = c.wr_id
                        LEFT JOIN services s
                            ON c.service_id = s.service_id
                        LEFT JOIN business_units bu
                            ON b.business_unit = bu.code AND b.org_code = bu.org_code
                        LEFT JOIN service_details sd
                            ON c.detail_id = sd.detail_id
                        WHERE
                            (a.action_status IS NULL OR a.action_status = '')
                            AND a.approval_type IN ('Pending Team Lead Approval', 'Pending Overall Lead Approval')
                            AND a.org_code = %s
                            AND a.acted_by = %s
                        GROUP BY a.id 
                        ORDER BY a.requested_datetime DESC"""
                data1 = (org_code, acted_user)

            elif "team lead" in role_titles:
                sql1 = """SELECT 
                            a.id AS id,
                            a.txn_type AS txn_type,
                            a.txn_reference AS txn_reference,
                            a.description AS description,
                            a.approval_type AS approval_type,
                            a.requested_by AS requested_by,
                            a.requested_datetime AS requested_datetime,
                            a.action_status AS action_status,
                            a.acted_by AS acted_by,
                            a.acted_datetime AS acted_datetime,
                            a.comment AS comment,
                            a.org_code AS org_code,
                            b.wr_id AS wr_id,
                            b.wo_number AS wo_number, 
                            b.wo_code AS wo_code,
                            b.job_end_date AS job_end_date,
                            b.project_name AS project_name,
                            b.project_description AS project_description, 
                            c.service_id AS service_id,
                            s.description AS scope,
                            bu.description AS company,
                            bu.acronym AS company_acronym,
                            GROUP_CONCAT(
                              DISTINCT sd.description
                              ORDER BY sd.description
                              SEPARATOR ', '
                            ) AS sub_scope,
                            b.wo_description AS wo_description
                        FROM approval_requests a
                        LEFT JOIN work_orders b
                            ON a.txn_reference = b.wo_number
                        LEFT JOIN (
                            SELECT rs.wr_id, rs.service_id, rs.detail_id 
                            FROM requested_services rs
                            INNER JOIN (
                                SELECT wr_id, MIN(id) AS first_id
                                FROM requested_services
                                GROUP BY wr_id
                            ) x
                                ON x.wr_id = rs.wr_id
                            AND x.first_id = rs.id
                        ) c
                            ON b.wr_id = c.wr_id
                        LEFT JOIN services s
                            ON c.service_id = s.service_id
                        LEFT JOIN business_units bu
                            ON b.business_unit = bu.code AND b.org_code = bu.org_code
                        LEFT JOIN service_details sd
                            ON c.detail_id = sd.detail_id
                        WHERE
                            (a.action_status IS NULL OR a.action_status = '')
                            AND a.approval_type IN ('Pending Team Lead Approval')
                            AND a.org_code = %s
                            AND a.acted_by = %s
                        GROUP BY a.id
                        ORDER BY a.requested_datetime DESC"""
                data1 = (org_code, acted_user)

            elif "manager" in role_titles:
                sql1 = """SELECT 
                            a.id AS id,
                            a.txn_type AS txn_type,
                            a.txn_reference AS txn_reference,
                            a.description AS description,
                            a.approval_type AS approval_type,
                            a.requested_by AS requested_by,
                            a.requested_datetime AS requested_datetime,
                            a.action_status AS action_status,
                            a.acted_by AS acted_by,
                            a.acted_datetime AS acted_datetime,
                            a.comment AS comment,
                            a.org_code AS org_code,
                            b.wr_id AS wr_id,
                            b.wo_number AS wo_number, 
                            b.wo_code AS wo_code,
                            b.job_end_date AS job_end_date,
                            b.project_name AS project_name,
                            b.project_description AS project_description, 
                            c.service_id AS service_id,
                            s.description AS scope,
                            bu.description AS company,
                            bu.acronym AS company_acronym,
                            GROUP_CONCAT(
                              DISTINCT sd.description
                              ORDER BY sd.description
                              SEPARATOR ', '
                            ) AS sub_scope,
                            b.wo_description AS wo_description
                        FROM approval_requests a
                        LEFT JOIN work_orders b
                            ON a.txn_reference = b.wo_number
                        LEFT JOIN (
                            SELECT rs.wr_id, rs.service_id, rs.detail_id 
                            FROM requested_services rs
                            INNER JOIN (
                                SELECT wr_id, MIN(id) AS first_id
                                FROM requested_services
                                GROUP BY wr_id
                            ) x
                                ON x.wr_id = rs.wr_id
                            AND x.first_id = rs.id
                        ) c
                            ON b.wr_id = c.wr_id
                        LEFT JOIN services s
                            ON c.service_id = s.service_id
                        LEFT JOIN business_units bu
                            ON b.business_unit = bu.code AND b.org_code = bu.org_code
                        LEFT JOIN service_details sd
                            ON c.detail_id = sd.detail_id
                        WHERE
                            (a.action_status IS NULL OR a.action_status = '')
                            AND a.approval_type IN ('Pending Overall Lead Approval')
                            AND a.org_code = %s
                            AND a.acted_by = %s
                        GROUP BY a.id 
                        ORDER BY a.requested_datetime DESC"""
                data1 = (org_code, acted_user)

            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "WR & WO for Approval retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No WR or WO for Approval found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrive WR and WO for Approval",
                "error": str(e)
            }), 500


    #--- get allowed pre-approvers of certain work order ----#
    @app.route('/getallowedpreapprovers', methods=['GET'])
    def getallowedpreapprovers():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wr_id' in request.args:
            wr_id = request.args["wr_id"]
        else:
            return "Error: No WR ID field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT user FROM work_order_team WHERE role = %s AND wr_id = %s AND org_code = %s"""
            data1 = ("team lead", wr_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Pre-approvers retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No pre-approvers found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrive pre-approvers",
                "error": str(e)
            }), 500


    #--- get allowed approvers of certain work order ----#
    @app.route('/getallowedapprovers', methods=['GET'])
    def getallowedapprovers():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."

        if 'wr_id' in request.args:
            wr_id = request.args["wr_id"]
        else:
            return "Error: No WR ID field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT user FROM work_order_team WHERE role = %s AND wr_id = %s AND org_code = %s"""
            data1 = ("manager", wr_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Approvers retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No approvers found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrive approvers",
                "error": str(e)
            }), 500
        

    #--- get all work logs per user ----#
    @app.route('/getworklogs', methods=['GET'])
    def getworklogs():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'email_address' in request.args:
            email_address = request.args['email_address']
        else:
            return "Error: No Email Address field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT * FROM work_logs WHERE email_address = %s AND org_code = %s ORDER BY log_datetime DESC"""
            data1 = (email_address, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Work Logs retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Work Logs found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrive work logs",
                "error": str(e)
            }), 500


    #--- get all timesheet per user ----#
    @app.route('/gettimesheet', methods=['GET'])
    def gettimesheet():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'work_log_id' in request.args:
            work_log_id = request.args['work_log_id']
        else:
            return "Error: No Work Log Id field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            sql1 = """SELECT * FROM timesheets WHERE work_log_id = %s AND org_code = %s ORDER BY start DESC"""
            data1 = (work_log_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Timesheets retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Timesheets found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrive timesheets",
                "error": str(e)
            }), 500


    #--- get all asigned materials per supplier ----#
    @app.route('/getassignedmaterials', methods=['GET'])
    def getassignedmaterials():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'supplier_id' in request.args:
            supplier_id = request.args['supplier_id']
        else:
            return "Error: No Supplier ID field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """SELECT a.supplier_id AS supplier_id, a.item_code AS item_code, b.description AS description FROM supplier_materials a LEFT JOIN physical_items b ON a.item_code = b.item_code WHERE a.supplier_id = %s AND a.org_code = %s ORDER by description"""
            data1 = (supplier_id, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are work requests
            if result:
                return jsonify({
                    "message": "Materials Assigned retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No materials found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve materials",
                "error": str(e)
            }), 500


    #--- get work order CU alterations per CU ----#
    @app.route('/getwocu_alterations', methods=['GET'])
    def getwocu_alterations():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'cu_code' in request.args:
            cu_code = request.args['cu_code']
        else:
            return "Error: No CU Code field provided. Please specify it."
            
        if 'design_type' in request.args:
            design_type = request.args['design_type']
        else:
            return "Error: No Design Type field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            if design_type == "SA":
                sql1 = """SELECT * FROM sa_cu_alterations WHERE org_code = %s AND wo_number = %s AND cu_code = %s ORDER BY created_datetime DESC"""
            else:
                sql1 = """SELECT * FROM wo_cu_alterations WHERE org_code = %s AND wo_number = %s AND cu_code = %s ORDER BY created_datetime DESC"""
                
            data1 = (org_code, wo_number, cu_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Alterations retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Alterations found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU alterations",
                "error": str(e)
            }), 500


    #--- get work order CU alterations ----#
    @app.route('/getwocu_alterationsall', methods=['GET'])
    def getwocu_alterationsall():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        if 'design_type' in request.args:
            design_type = request.args['design_type']
        else:
            return "Error: No Design Type field provided. Please specify it."
        
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            if design_type == "SA":
                sql1 = """SELECT * FROM sa_cu_alterations WHERE org_code = %s AND wo_number = %s ORDER BY cu_title"""
            else:
                sql1 = """SELECT * FROM wo_cu_alterations WHERE org_code = %s AND wo_number = %s ORDER BY cu_title"""
                
            data1 = (org_code, wo_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "CU Alterations retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No CU Alterations found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU alterations",
                "error": str(e)
            }), 500


    #--- get work order approval history ----#
    @app.route('/getwoapprovalhistory', methods=['GET'])
    def getwoapprovalhistory():
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
        
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."    
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            
            sql1 = """SELECT * FROM approval_requests WHERE org_code = %s AND txn_type = %s AND txn_reference = %s ORDER BY requested_datetime DESC"""
                
            data1 = (org_code, 'Work Order', wo_number)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Approval History retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No Approval History found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve Approval History",
                "error": str(e)
            }), 500


    # --- Get email address to check if it exists ---
    @app.route('/getemailaddress', methods=['GET'])
    def getemailaddress():
        org_code = request.args.get('org_code')
        email_address = request.args.get('email_address')

        if not org_code:
            return jsonify({
                "message": "Error: No Organization Code field provided. Please specify it.",
                "result": False
            }), 400

        if not email_address:
            return jsonify({
                "message": "Error: No Email Address field provided. Please specify it.",
                "result": False
            }), 400

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """SELECT 1 FROM app_users WHERE org_code = %s AND user = %s"""
            cur.execute(sql, (org_code, email_address))
            record = cur.fetchone()

            if record:
                return jsonify({
                    "message": "Email Address already exists",
                    "result": True
                }), 200
            else:
                return jsonify({
                    "message": "Email Address not found",
                    "result": False
                }), 200

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve Email Address",
                "error": str(e),
                "result": False
            }), 500
        

    # --- Get Material CU Code to check if it exists ---
    @app.route('/getcucode', methods=['GET'])
    def getcucode():
        org_code = request.args.get('org_code')
        cu_code = request.args.get('cu_code')

        if not org_code:
            return jsonify({
                "message": "Error: No Organization Code field provided. Please specify it.",
                "result": False
            }), 400

        if not cu_code:
            return jsonify({
                "message": "Error: No CU Code field provided. Please specify it.",
                "result": False
            }), 400

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """SELECT 1 FROM physical_compatible_units WHERE org_code = %s AND code = %s"""
            cur.execute(sql, (org_code, cu_code))
            record = cur.fetchone()

            if record:
                return jsonify({
                    "message": "CU Code already exists",
                    "result": True
                }), 200
            else:
                return jsonify({
                    "message": "CU Code not found",
                    "result": False
                }), 200

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve CU Code",
                "error": str(e),
                "result": False
            }), 500
        

    #--- get work order material CU alterations ----#
    @app.route('/getmaterialcualterations', methods=['GET'])
    def getmaterialcualterations():
        if 'wo_number' in request.args:
            wo_number = request.args['wo_number']
        else:
            return "Error: No WO Number field provided. Please specify it."
            
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor(pymysql.cursors.DictCursor)  # Use dictionary cursor
            
            '''
            sql1 = """
                SELECT 
                    a.cu_code,
                    pc.title,
                    a.item_code,
                    pi.description,
                    a.quantity AS quantity_in_base,
                    b.quantity AS quantity_in_design,
                    CASE 
                        WHEN b.item_code IS NULL THEN 'Missing from the work order design'
                        WHEN a.quantity != b.quantity THEN 'Quantity mismatch'
                    END AS reason
                FROM physical_cu_items a
                JOIN (
                    SELECT DISTINCT cu_code 
                    FROM wo_task_physical_items 
                    WHERE wo_number = %s AND org_code = %s 
                ) used_cus ON a.cu_code = used_cus.cu_code
                LEFT JOIN (
                    SELECT * FROM wo_task_physical_items 
                    WHERE wo_number = %s AND org_code = %s 
                ) b ON a.cu_code = b.cu_code AND a.item_code = b.item_code
                LEFT JOIN physical_items pi ON a.item_code = pi.item_code
                LEFT JOIN physical_compatible_units pc ON a.cu_code = pc.code
                WHERE b.item_code IS NULL OR a.quantity != b.quantity

                UNION

                SELECT 
                    b.cu_code,
                    pc.title,
                    b.item_code,
                    pi.description,
                    NULL AS quantity_in_base,
                    b.quantity AS quantity_in_design,
                    'Extra item in work order design' AS reason
                FROM (
                    SELECT * FROM wo_task_physical_items 
                    WHERE wo_number = %s AND org_code = %s 
                ) b
                LEFT JOIN physical_cu_items a 
                    ON a.cu_code = b.cu_code AND a.item_code = b.item_code
                LEFT JOIN physical_items pi ON b.item_code = pi.item_code
                LEFT JOIN physical_compatible_units pc ON b.cu_code = pc.code
                WHERE a.item_code IS NULL
            """
            '''
            sql1 = """
                SELECT * FROM (
                    SELECT 
                        a.cu_code,
                        pc.title,
                        a.item_code,
                        pi.description,
                        a.quantity AS quantity_in_base,
                        b.quantity AS quantity_in_design,
                        CASE 
                            WHEN b.item_code IS NULL THEN 'Missing from the work order design'
                            WHEN a.quantity != b.quantity THEN 'Quantity mismatch'
                        END AS reason
                    FROM physical_cu_items a
                    JOIN (
                        SELECT DISTINCT cu_code 
                        FROM wo_task_physical_items 
                        WHERE wo_number = %s AND org_code = %s 
                    ) used_cus ON a.cu_code = used_cus.cu_code
                    LEFT JOIN (
                        SELECT * FROM wo_task_physical_items 
                        WHERE wo_number = %s AND org_code = %s 
                    ) b ON a.cu_code = b.cu_code AND a.item_code = b.item_code
                    LEFT JOIN physical_items pi ON a.item_code = pi.item_code
                    LEFT JOIN physical_compatible_units pc ON a.cu_code = pc.code
                    WHERE b.item_code IS NULL OR a.quantity != b.quantity

                    UNION

                    SELECT 
                        b.cu_code,
                        pc.title,
                        b.item_code,
                        pi.description,
                        NULL AS quantity_in_base,
                        b.quantity AS quantity_in_design,
                        'Extra item in work order design' AS reason
                    FROM (
                        SELECT * FROM wo_task_physical_items 
                        WHERE wo_number = %s AND org_code = %s 
                    ) b
                    LEFT JOIN physical_cu_items a 
                        ON a.cu_code = b.cu_code AND a.item_code = b.item_code
                    LEFT JOIN physical_items pi ON b.item_code = pi.item_code
                    LEFT JOIN physical_compatible_units pc ON b.cu_code = pc.code
                    WHERE a.item_code IS NULL
                ) AS mismatches
                ORDER BY title, cu_code, item_code
            """


            data1 = (wo_number, org_code, wo_number, org_code, wo_number, org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchall()  # Fetch all rows
            
            app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
            
            # Check if there are records
            if result:
                return jsonify({
                    "message": "Alterations retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No alterations found",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve alterations",
                "error": str(e)
            }), 500


    # --- Get tasks from asana chatbox ---
    @app.route('/getasanachattasks', methods=['GET'])
    def getasanachattasks():
        org_code = request.args.get('org_code')
        projectId = request.args.get('project_gid')

        if not org_code:
            return jsonify({
                "message": "Error: No Organization Code field provided. Please specify it.",
                "result": False
            }), 400

        if not projectId:
            return jsonify({
                "message": "Error: No Project GID field provided. Please specify it.",
                "result": False
            }), 400

        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()

            sql = """SELECT DISTINCT task_gid FROM app_chatbox WHERE org_code = %s AND project_gid = %s"""
            cur.execute(sql, (org_code, projectId))
            result = cur.fetchall()

            if result:
                return jsonify({
                    "message": "Tasks GIDs retrieved successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "Tasks GID not found",
                    "result": []
                }), 200

        except Exception as e:
            return jsonify({
                "message": "Failed to retrieve Task GIDs",
                "error": str(e),
                "result": False
            }), 500


    #--- get open work orders count for certain work request ----#
    @app.route('/getopenworkorders', methods=['GET'])
    def getopenworkorders():
        if 'wr_id' in request.args:
            wr_id = request.args['wr_id']
        else:
            return "Error: No Work Request ID field provided. Please specify it."
        
        if 'org_code' in request.args:
            org_code = request.args['org_code']
        else:
            return "Error: No Organization Code field provided. Please specify it."
            
        try:
            conn = dbconnect.getConnection()
            cur = conn.cursor()
            
            sql1 = """
                SELECT COUNT(*) AS open_wo_count FROM work_orders WHERE wr_id = %s AND status != %s AND org_code = %s 
                """
            data1 = (wr_id, 'Completed', org_code)
            
            cur.execute(sql1, data1)
            result = cur.fetchone()

            if result:
                app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

                return jsonify({
                    "message": "Open Work Order Count generated successfully",
                    "result": result
                }), 200
            else:
                return jsonify({
                    "message": "No open work order count generated",
                    "result": []
                }), 404
            
        except Exception as e:
            return jsonify({
                "message": "Failed to count open work order",
                "error": str(e)
            }), 500


   