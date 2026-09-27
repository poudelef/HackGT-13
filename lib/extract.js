const fs = require("fs");
const { extractText, getDocumentProxy } = require("unpdf");
const OpenAI = require("openai");
const { DOCUMENT_SCHEMAS, CLINICAL_DOCUMENT_SCHEMA } = require("./schemas");

const XAI_BASE_URL = "https://api.x.ai/v1";
const GROK_MODEL = process.env.GROK_MODEL || "grok-4-fast-non-reasoning";

function getClient() {
  const apiKey = process.env.XAI_API_KEY;
  if (!apiKey || apiKey.includes("...")) {
    throw new Error("Set XAI_API_KEY in the .env file before uploading a PDF.");
  }
  return new OpenAI({
    apiKey,
    baseURL: XAI_BASE_URL,
    timeout: 120000,
  });
}

async function extractRawTextFromPdf(filePath) {
  const buffer = fs.readFileSync(filePath);
  let pdf;
  try {
    pdf = await getDocumentProxy(new Uint8Array(buffer), { verbosity: 0 });
  } catch {
    throw new Error("This PDF could not be read. Upload a standard text PDF.");
  }
  const { text } = await extractText(pdf, { mergePages: true });
  return Array.isArray(text) ? text.join("\n") : String(text || "");
}

async function extractStructuredData(documentType, rawText) {
  const config = DOCUMENT_SCHEMAS[documentType];
  if (!config) {
    throw new Error(`Unknown document type: ${documentType}`);
  }
  if (!rawText.trim()) {
    throw new Error("No text could be read from this PDF. It may be a scanned image.");
  }

  const systemPrompt = `You are a medical document data-extraction assistant.
You will be given raw text extracted from a "${config.description}" PDF.
Extract every relevant fact and respond with ONLY a valid JSON object matching this schema (no markdown, no explanation, no code fences):

${JSON.stringify(config.schema, null, 2)}

Rules:
- This JSON will later be inserted into a relational database. Use the field names exactly.
- Do not invent patient_id, provider_id, or any other surrogate key. Those are assigned by the database.
- If a field is not present in the text, use null. Use an empty array when a list section is absent. Do not invent clinical data, codes, dates, or names.
- Split person names into first_name and last_name.
- Dates must be YYYY-MM-DD.
- Use only the enum values shown. If the document's wording does not match an enum, pick the closest allowed value or null.
- Keep letter_text, findings, impression, and clinical_notes as the source wording, not a paraphrase that drops facts.`;

  const grok = getClient();
  const completion = await grok.chat.completions.create({
    model: GROK_MODEL,
    temperature: 0,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: rawText.slice(0, 100000) },
    ],
  });

  const jsonText = completion.choices[0].message.content;
  return JSON.parse(jsonText);
}

async function processPdf(filePath, documentType) {
  const rawText = await extractRawTextFromPdf(filePath);
  const structuredData = await extractStructuredData(documentType, rawText);
  return { rawText, structuredData };
}

async function extractClinicalDocument(rawText) {
  if (!rawText.trim()) {
    throw new Error("No text could be read from this PDF. It may be a scanned image.");
  }

  const systemPrompt = `You are a medical document data-extraction assistant.
You will be given raw text from one clinical PDF uploaded by a doctor.
Decide which document type it is, then extract every relevant fact into this schema (no markdown, no explanation, no code fences):

${JSON.stringify(CLINICAL_DOCUMENT_SCHEMA, null, 2)}

Rules:
- This JSON will later be inserted into a relational database. Use the field names exactly.
- Do not invent patient_id, provider_id, or any other surrogate key. Those are assigned by the database.
- If a field or section is not present in the text, use null. Use an empty array when a list section is absent. Do not invent clinical data, codes, dates, or names.
- A single PDF may fill more than one section. Extract all of them.
- Split person names into first_name and last_name.
- Dates must be YYYY-MM-DD.
- document_type must be one of: ${[...Object.keys(DOCUMENT_SCHEMAS), "OTHER"].join(", ")}.
- Use only the enum values shown. If the document's wording does not match an enum, pick the closest allowed value or null.
- Keep letter_text, findings, impression, and clinical_notes as the source wording, not a paraphrase that drops facts.`;

  const grok = getClient();
  const completion = await grok.chat.completions.create({
    model: GROK_MODEL,
    temperature: 0,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: rawText.slice(0, 100000) },
    ],
  });

  const jsonText = completion.choices[0].message.content;
  const structuredData = JSON.parse(jsonText);
  const allowed = new Set([...Object.keys(DOCUMENT_SCHEMAS), "OTHER"]);
  if (!allowed.has(structuredData.document_type)) {
    structuredData.document_type = "OTHER";
  }
  return structuredData;
}

async function processClinicalPdf(filePath) {
  const rawText = await extractRawTextFromPdf(filePath);
  const structuredData = await extractClinicalDocument(rawText);
  return { rawText, structuredData };
}

module.exports = {
  extractRawTextFromPdf,
  extractStructuredData,
  processPdf,
  processClinicalPdf,
};
