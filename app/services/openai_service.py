import base64
import io
import json
import logging
from typing import Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None

EXTRACTION_PROMPT = """You are a medical document parser. Extract all information from this medical report image and return ONLY a valid JSON object with these fields:
- patientName: string or null
- dateOfBirth: string (YYYY-MM-DD) or null
- reportDate: string (YYYY-MM-DD) or null
- reportType: string (e.g. "Blood Panel", "X-Ray", "MRI") or null
- doctorName: string or null
- hospitalName: string or null
- findings: array of {label: string, value: string, unit: string, referenceRange: string, flag: "NORMAL"|"HIGH"|"LOW"|"CRITICAL"|null}
- diagnosis: string or null
- recommendations: string or null
- rawText: string (all text found in the document)
Return only the JSON object, no markdown, no explanation."""


def _get_client() -> OpenAI:
    """Return a cached OpenAI client instance."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _pdf_to_jpeg_bytes(pdf_bytes: bytes) -> bytes:
    """Rasterize the first page of a PDF to JPEG bytes using pdf2image + Pillow.

    Falls back gracefully if poppler is not installed by raising a RuntimeError
    with a helpful message.
    """
    try:
        from pdf2image import convert_from_bytes
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image and Pillow are required for PDF processing. "
            "Install them with: pip install pdf2image Pillow"
        ) from exc

    try:
        pages = convert_from_bytes(pdf_bytes, first_page=1, last_page=1, dpi=200)
        if not pages:
            raise ValueError("PDF appears to have no pages.")
        first_page: Image.Image = pages[0]
        buf = io.BytesIO()
        # Convert to RGB in case the image is RGBA or palette-based
        first_page.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception as exc:
        logger.error("Failed to convert PDF to image: %s", exc)
        raise


def _image_bytes_to_jpeg(image_bytes: bytes, file_type: str) -> bytes:
    """Ensure image bytes are in JPEG format that GPT-4o can handle.

    For JPEG/JPG inputs the bytes are returned as-is; PNGs are converted.
    """
    if file_type in ("image/jpeg", "image/jpg"):
        return image_bytes

    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for image processing.") from exc

    buf = io.BytesIO(image_bytes)
    img = Image.open(buf)
    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=85)
    return out.getvalue()


INSIGHTS_SYSTEM_PROMPT = """You are a medical AI assistant that analyzes patient medical reports and provides clear, helpful health observations.
You must respond ONLY with valid JSON matching this exact structure:
{
  "summary": "A 2-3 sentence overall health summary",
  "observations": [
    {
      "title": "Short title",
      "detail": "Detailed explanation",
      "severity": "info|warning|critical|positive"
    }
  ],
  "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"],
  "disclaimer": "Standard medical disclaimer"
}

Rules:
- severity "critical" = values flagged CRITICAL or very abnormal
- severity "warning" = values flagged HIGH or LOW
- severity "positive" = normal results or improving trends
- severity "info" = general observations
- Be concise but informative
- Always include a disclaimer about consulting a doctor
- Focus on patterns across multiple reports if available"""


def generate_insights(report_summary: str) -> dict:
    """Generate AI health insights from a text summary of medical reports using GPT-4o-mini."""
    client = _get_client()
    logger.info("Calling GPT-4o-mini for health insights generation.")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Please analyze the following medical report data and provide AI health observations:\n\n"
                    + report_summary
                ),
            },
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or ""
    if not content:
        raise ValueError("Empty response from OpenAI")

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse insights response as JSON: %s", exc)
        raise ValueError(f"Failed to parse insights response: {exc}") from exc


def extract_report_content(file_bytes: bytes, file_type: str) -> dict:
    """Extract structured medical data from a report file using GPT-4o vision.

    Args:
        file_bytes: Raw bytes of the uploaded file.
        file_type: MIME type, e.g. "application/pdf", "image/jpeg", "image/png".

    Returns:
        A dict containing the extracted fields defined in EXTRACTION_PROMPT.

    Raises:
        ValueError: If the OpenAI response cannot be parsed as JSON.
        RuntimeError: If PDF/image conversion fails.
        openai.OpenAIError: On API errors.
    """
    # Step 1: Convert to JPEG bytes suitable for vision API
    if file_type == "application/pdf":
        logger.info("Converting PDF to JPEG for vision extraction.")
        jpeg_bytes = _pdf_to_jpeg_bytes(file_bytes)
    else:
        logger.info("Preparing image bytes (%s) for vision extraction.", file_type)
        jpeg_bytes = _image_bytes_to_jpeg(file_bytes, file_type)

    # Step 2: Base64-encode
    b64_image = base64.b64encode(jpeg_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64_image}"

    # Step 3: Call GPT-4o with vision
    client = _get_client()
    logger.info("Calling GPT-4o for medical report extraction.")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
        max_tokens=4096,
        temperature=0,
    )

    raw_content = response.choices[0].message.content or ""
    logger.info("GPT-4o returned %d characters.", len(raw_content))

    # Step 4: Parse JSON response
    # Strip markdown code fences if the model added them despite instructions
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Remove first and last fence lines
        inner_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            if line.startswith("```") and in_block:
                break
            inner_lines.append(line)
        cleaned = "\n".join(inner_lines)

    try:
        extracted = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse GPT-4o response as JSON: %s\nRaw: %s", exc, raw_content[:500])
        raise ValueError(
            f"GPT-4o returned non-JSON content. Parse error: {exc}"
        ) from exc

    # Ensure findings is always a list even if the model returned null/missing
    if not isinstance(extracted.get("findings"), list):
        extracted["findings"] = []

    return extracted
