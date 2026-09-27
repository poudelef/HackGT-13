require("dotenv").config();

const express = require("express");
const multer = require("multer");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const { processClinicalPdf } = require("./lib/extract");
const { pool, databaseErrorMessage } = require("./lib/db");
const { loadDashboard } = require("./lib/patientRecords");
const { findProvider, loadPatientForDoctor, createAuthorization, DOCUMENT_TYPES } = require("./lib/doctorRecords");
const { normalizeExtracted } = require("./lib/chartMerge");

const app = express();
const PORT = process.env.PORT || 3000;

const ROOT = __dirname;
const UPLOAD_DIR = path.join(ROOT, "uploads");
const DATA_DIR = path.join(ROOT, "data");
const CASES_FILE = path.join(DATA_DIR, "cases.json");

fs.mkdirSync(UPLOAD_DIR, { recursive: true });
fs.mkdirSync(DATA_DIR, { recursive: true });

function loadCases() {
  try {
    const raw = fs.readFileSync(CASES_FILE, "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveCases(cases) {
  fs.writeFileSync(CASES_FILE, JSON.stringify(cases, null, 2), "utf8");
}

let cases = loadCases();

function normalizeId(id) {
  return String(id || "").trim().toLowerCase();
}

const caseStorage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOAD_DIR),
  filename: (_req, file, cb) => {
    const unique = `${Date.now()}-${crypto.randomBytes(8).toString("hex")}`;
    const safeOriginal = path.basename(file.originalname).replace(/[^\w.\-]+/g, "_");
    cb(null, `${unique}-${safeOriginal}`);
  },
});

function pdfOnly(_req, file, cb) {
  const isPdfMime = file.mimetype === "application/pdf";
  const isPdfExt = path.extname(file.originalname).toLowerCase() === ".pdf";
  if (isPdfMime && isPdfExt) {
    cb(null, true);
  } else {
    cb(new Error("Only PDF files are allowed."));
  }
}

const caseUpload = multer({
  storage: caseStorage,
  fileFilter: pdfOnly,
  limits: {
    files: 10,
    fileSize: 15 * 1024 * 1024,
  },
});

function sidecarName(pdfFilename, extension) {
  return pdfFilename.replace(/\.pdf$/i, "") + extension;
}

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(ROOT, "public")));

app.post("/api/cases", (req, res) => {
  caseUpload.array("pdfs", 10)(req, res, async (err) => {
    if (err) {
      const message =
        err instanceof multer.MulterError
          ? err.code === "LIMIT_FILE_COUNT"
            ? "You can upload at most 10 PDF files."
            : err.message
          : err.message || "Upload failed.";
      return res.status(400).json({ ok: false, error: message });
    }

    const patientName = String(req.body.patientName || "").trim();
    const patientId = String(req.body.patientId || "").trim();
    const patientAge = String(req.body.patientAge || "").trim();
    const medicalInfo = String(req.body.medicalInfo || "").trim();
    const doctorName = String(req.body.doctorName || "Dr. Sarah Chen").trim();

    if (!patientName || !patientId || !patientAge) {
      return res.status(400).json({
        ok: false,
        error: "Patient name, ID, and age are required.",
      });
    }

    const ageNumber = Number(patientAge);
    if (!Number.isFinite(ageNumber) || ageNumber < 0 || ageNumber > 130) {
      return res.status(400).json({ ok: false, error: "Enter a valid patient age." });
    }

    const files = [];
    for (const file of req.files || []) {
      const record = {
        originalName: file.originalname,
        storedName: file.filename,
        size: file.size,
        documentType: null,
        dataFile: null,
        extractionError: null,
      };

      try {
        const pdfPath = path.join(UPLOAD_DIR, file.filename);
        const extractedAt = new Date().toISOString();
        const { rawText, structuredData } = await processClinicalPdf(pdfPath);
        const dataFile = sidecarName(file.filename, ".json");
        const saved = {
          document_type: structuredData.document_type || "OTHER",
          file_path: path.relative(ROOT, pdfPath).split(path.sep).join("/"),
          uploaded_at: extractedAt,
          extracted_at: extractedAt,
          tables: structuredData,
        };
        fs.writeFileSync(path.join(UPLOAD_DIR, dataFile), JSON.stringify(saved, null, 2));
        fs.writeFileSync(path.join(UPLOAD_DIR, sidecarName(file.filename, ".txt")), rawText);
        record.documentType = saved.document_type;
        record.dataFile = dataFile;
        record.tables = saved;
      } catch (error) {
        console.error(error);
        record.extractionError = error.message || "Failed to read this PDF.";
      }

      files.push(record);
    }

    const record = {
      id: crypto.randomUUID(),
      patientName,
      patientId,
      patientAge: ageNumber,
      medicalInfo,
      doctorName,
      files: files.map(({ tables, ...file }) => file),
      status: "Waiting for insurance to review",
      submittedAt: new Date().toISOString(),
    };

    const existingIndex = cases.findIndex(
      (item) => normalizeId(item.patientId) === normalizeId(patientId)
    );
    if (existingIndex >= 0) {
      cases[existingIndex] = record;
    } else {
      cases.push(record);
    }
    saveCases(cases);

    return res.json({
      ok: true,
      message: "Case submitted successfully.",
      case: {
        ...publicCase(record),
        files,
      },
    });
  });
});

function publicCase(record) {
  return {
    patientName: record.patientName,
    patientId: record.patientId,
    patientAge: record.patientAge,
    medicalInfo: record.medicalInfo,
    doctorName: record.doctorName,
    files: (record.files || []).map((file) => ({
      originalName: file.originalName,
      size: file.size,
    })),
    status: record.status,
    submittedAt: record.submittedAt,
  };
}

function sendDoctorError(res, err) {
  if (err.status && err.status < 500) {
    return res.status(err.status).json({ ok: false, error: err.message });
  }
  console.error(err);
  return res.status(503).json({ ok: false, error: databaseErrorMessage(err) });
}

app.post("/api/doctor/login", async (req, res) => {
  try {
    const provider = await findProvider(req.body.providerId, req.body.npi);
    if (!provider) {
      return res.status(401).json({
        ok: false,
        error: "Not authorized. That provider ID and NPI do not match.",
      });
    }
    return res.json({
      ok: true,
      provider: {
        providerId: provider.provider_id,
        npi: provider.npi,
        firstName: provider.first_name,
        lastName: provider.last_name,
        specialty: provider.specialty,
        clinicName: provider.clinic_name,
      },
    });
  } catch (err) {
    return sendDoctorError(res, err);
  }
});

app.post("/api/doctor/patient", async (req, res) => {
  try {
    const result = await loadPatientForDoctor(
      req.body.providerId,
      req.body.npi,
      req.body.patientName,
      req.body.patientId
    );
    if (!result.record) {
      return res.status(404).json({ ok: false, error: "Patient not found." });
    }
    return res.json({ ok: true, record: result.record });
  } catch (err) {
    return sendDoctorError(res, err);
  }
});

app.post("/api/doctor/authorization", (req, res) => {
  caseUpload.array("pdfs", 10)(req, res, async (err) => {
    if (err) {
      const message = err instanceof multer.MulterError ? err.message : err.message || "Upload failed.";
      return res.status(400).json({ ok: false, error: message });
    }

    const files = req.files || [];
    if (!files.length) {
      return res.status(400).json({ ok: false, error: "Upload at least one PDF." });
    }
    for (const file of files) {
      const isPdf = file.mimetype === "application/pdf" || file.originalname.toLowerCase().endsWith(".pdf");
      if (!isPdf) {
        return res.status(400).json({ ok: false, error: "Only PDF files are allowed." });
      }
    }

    try {
      const extracted = [];
      const pdfCharts = [];
      const readyFiles = [];
      for (const file of files) {
        const pdfPath = path.join(UPLOAD_DIR, file.filename);
        const record = {
          originalName: file.originalname,
          extractionError: null,
        };
        try {
          const extractedAt = new Date().toISOString();
          const { rawText, structuredData } = await processClinicalPdf(pdfPath);
          const dataFile = sidecarName(file.filename, ".json");
          const payload = {
            document_type: structuredData.document_type || "OTHER",
            file_path: path.relative(ROOT, pdfPath).split(path.sep).join("/"),
            uploaded_at: extractedAt,
            extracted_at: extractedAt,
            tables: structuredData,
          };
          fs.writeFileSync(path.join(UPLOAD_DIR, dataFile), JSON.stringify(payload, null, 2));
          fs.writeFileSync(path.join(UPLOAD_DIR, sidecarName(file.filename, ".txt")), rawText);
          file.documentType = DOCUMENT_TYPES.includes(payload.document_type) ? payload.document_type : "PA_FORM";
          record.filePath = payload.file_path;
          pdfCharts.push(normalizeExtracted(structuredData));
          readyFiles.push(file);
        } catch (error) {
          console.error(error);
          record.extractionError = error.message || "Failed to read this PDF.";
        }
        extracted.push(record);
      }

      if (!pdfCharts.length) {
        const reason = extracted.find((file) => file.extractionError)?.extractionError || "Could not read the PDF.";
        return res.status(400).json({ ok: false, error: reason });
      }

      const saved = await createAuthorization(req.body, readyFiles, pdfCharts);
      const chartFile = `${Date.now()}-${crypto.randomBytes(4).toString("hex")}-preauth-chart.json`;
      fs.writeFileSync(path.join(UPLOAD_DIR, chartFile), JSON.stringify(saved.chart, null, 2));
      for (const record of extracted) {
        if (!record.filePath || record.extractionError) continue;
        await pool.query(
          `UPDATE pa_documents SET extracted_at = NOW() WHERE pa_id = ? AND file_path = ?`,
          [saved.paId, record.filePath]
        );
      }

      return res.json({
        ok: true,
        paId: saved.paId,
        files: extracted.map((file) => ({
          originalName: file.originalName,
          extractionError: file.extractionError,
        })),
      });
    } catch (error) {
      return sendDoctorError(res, error);
    }
  });
});

app.post("/api/patient/status", async (req, res) => {
  const patientName = String(req.body.patientName || "").trim();
  const patientId = String(req.body.patientId || "").trim();

  if (!patientName || !patientId) {
    return res.status(400).json({
      ok: false,
      error: "Patient name and ID are required.",
    });
  }

  try {
    const record = await loadDashboard(patientName, patientId);
    if (!record) {
      return res.status(401).json({
        ok: false,
        error: "Not authorized. That name and ID do not match a patient.",
      });
    }
    return res.json({ ok: true, record });
  } catch (err) {
    console.error(err);
    return res.status(503).json({ ok: false, error: databaseErrorMessage(err) });
  }
});

app.use((err, _req, res, _next) => {
  if (err && err.type === "entity.parse.failed") {
    return res.status(400).json({ ok: false, error: "Invalid JSON body." });
  }
  console.error(err);
  res.status(500).json({ ok: false, error: "Server error." });
});

app.listen(PORT, () => {
  console.log(`Medical Case Portal running at http://localhost:${PORT}`);
});
