# DB Memray Analyzer

## 1. Which package/library does the sample program demonstrate?

This sample program primarily demonstrates **Memray** (Python memory profiler) for profiling query execution and generating flamegraphs.

It also uses:
- **FastAPI** to serve the web app and API endpoints
- **psutil** and **tracemalloc** for live memory stats

## 2. How does someone run your program?

From the project folder:

```bash
cd /mnt/pi/cs2613
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn memray psutil pydantic
uvicorn website:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## 3. What purpose does your program serve?

This program is a mini in-memory database + profiling dashboard.

It lets you:
- run SQL-like commands (`CREATE TABLE`, `INSERT`, `SELECT`, `UPDATE`, `DELETE`, `SHOW`, etc.)
- run bulk query scripts
- generate large synthetic datasets (for example 1000 random users in one command)
- profile queries with Memray and open flamegraphs
- monitor live memory usage and database stats

## 4. What would be some sample input/output?

### Sample input

```sql
DROP TABLE IF EXISTS *;
CREATE TABLE users (age int, id int PRIMARY KEY, fname str, lname str);
INSERT RANDOM USERS INTO users COUNT 1000 START_ID 1 AGE_RANGE (18, 90);
SELECT COUNT(*) FROM users;
SELECT * FROM users WHERE id = 1;
SHOW STATS;
```

### Sample output

```json
{
  "ok": true,
  "message": "Inserted 1000 random user row(s).",
  "generatedCount": 1000,
  "previewRows": [
    {"age": 42, "id": 1, "fname": "Ava", "lname": "Smith"}
  ]
}
```

```json
{
  "ok": true,
  "count": 1000
}
```

```json
{
  "ok": true,
  "stats": {
    "databaseId": 1,
    "databaseName": "AdrianDB",
    "tableCount": 1,
    "totalRows": 1000
  }
}
```
