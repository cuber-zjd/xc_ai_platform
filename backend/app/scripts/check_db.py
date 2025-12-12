import sys
import os
import pyodbc
import platform

MSSQL_HOST = "192.168.14.127"
MSSQL_USER = "sa"
MSSQL_PASS = "Xckg123456!"
MSSQL_DB = "ehr"

def test_ping():
    print(f"--- Pinging {MSSQL_HOST} ---")
    param = '-n' if platform.system().lower()=='windows' else '-c'
    res = os.system(f"ping {param} 1 {MSSQL_HOST}")
    if res == 0:
        print("Ping successful.")
    else:
        print("Ping failed! Check network/VPN.")

def list_drivers():
    print("\n--- Available ODBC Drivers ---")
    drivers = pyodbc.drivers()
    for d in drivers:
        print(f" - {d}")
    return drivers

def test_connection(driver_name):
    print(f"\n--- Testing Connection with Driver: {driver_name} ---")
    conn_str = (
        f"DRIVER={{{driver_name}}};"
        f"SERVER={MSSQL_HOST};"
        f"DATABASE={MSSQL_DB};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASS};"
        "TrustServerCertificate=yes;"
    )
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        print("SUCCESS! Connected.")
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        row = cursor.fetchone()
        print(f"Server Version: {row[0]}")
        conn.close()
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

if __name__ == "__main__":
    test_ping()
    drivers = list_drivers()
    
    # Try common drivers
    priority_drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server"
    ]
    
    connected = False
    for d in priority_drivers:
        if d in drivers:
            if test_connection(d):
                connected = True
                break
    
    if not connected:
        print("\nCould not connect with any priority driver. Trying all others...")
        for d in drivers:
            if d not in priority_drivers:
                if test_connection(d):
                    break
