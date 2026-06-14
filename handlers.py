import json
import pymysql
from flask import jsonify
import dbconnect

def handler_save_to_mysql(data):
    """Handler to save data to MySQL database."""
    try:
        # Extract data from the payload
        wr_id = data.get("wr_id")
        resource_type = data.get("resource_type")
        gid = data.get("gid")
        details = data.get("details")

        if not gid or not details:
            return {"error": "Missing required fields: gid or details"}, 400

        # Convert `details` to a JSON string if it isn't already
        if not isinstance(details, dict):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                return {"error": "Invalid JSON format in 'details' field."}, 400

        # Establish a connection to MySQL database
        conn = dbconnect.getConnection()
        cur = conn.cursor()

        # SQL query to insert data into work_mgt_data table
        sql = "INSERT INTO wr_pm_data (wr_id, resource_type, gid, details) VALUES (%s, %s, %s, %s)"
        cur.execute(sql, (wr_id, resource_type, gid, json.dumps(details)))

        # Commit the transaction
        conn.commit()

        return {"status_code": 200, "message": "Data saved successfully."}

    except pymysql.MySQLError as e:
        # Handle specific MySQL errors
        error_message = str(e)
        print(f"MySQL Error: {error_message}")
        return {"error": f"MySQL Error: {error_message}"}, 500

    except Exception as e:
        # Handle other exceptions
        error_message = str(e)
        print(f"General Error: {error_message}")
        return {"error": f"Internal server error: {error_message}"}, 500

    finally:
        # Close cursor and connection safely
        if 'cur' in locals() and cur:
            cur.close()
        if 'conn' in locals() and conn:
            conn.close()
