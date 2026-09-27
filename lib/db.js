const mysql = require("mysql2/promise");

const pool = mysql.createPool({
  host: process.env.DB_HOST || "localhost",
  port: Number(process.env.DB_PORT || 3306),
  user: process.env.DB_USER || "root",
  password: process.env.DB_PASSWORD || "",
  database: process.env.DB_NAME || "hackgt_db",
  waitForConnections: true,
  connectionLimit: 10,
  dateStrings: true,
});

function databaseErrorMessage(err) {
  if (err.code === "ER_ACCESS_DENIED_ERROR") {
    return "Database login failed. Set DB_PASSWORD in .env to your MySQL root password.";
  }
  if (err.code === "ER_BAD_DB_ERROR") {
    return "Database was not found. Check DB_NAME in .env (expected hackgt_db).";
  }
  if (err.code === "ECONNREFUSED" || err.code === "ENOTFOUND" || err.code === "ETIMEDOUT") {
    return "Could not connect to MySQL. Check that the server is running and DB_HOST in .env.";
  }
  if (err.code === "ER_NO_SUCH_TABLE") {
    return "A required table is missing in the database.";
  }
  return "Could not load patient records.";
}

module.exports = { pool, databaseErrorMessage };
