/**
 * Structured logging utility for React UI
 * Provides trace_id generation and structured log output
 */

export function generateTraceId() {
  // Generate short trace ID (8 chars) for readability
  return Math.random().toString(36).substring(2, 10);
}

export function redactUrl(url) {
  try {
    const urlObj = new URL(url);
    // Return host + path, no query params
    return `${urlObj.protocol}//${urlObj.host}${urlObj.pathname}`;
  } catch {
    return url.split('?')[0]; // Fallback
  }
}

export function logStructured(component, direction, event, summary, traceId = null, extra = {}) {
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 23);
  
  const parts = [`[${timestamp}]`];
  if (traceId) {
    parts.push(`[trace_id=${traceId}]`);
  }
  parts.push(`[${component}]`);
  parts.push(direction);
  parts.push(`[${event}]`);
  parts.push(summary);
  
  // Add optional fields
  if (Object.keys(extra).length > 0) {
    const optionalParts = [];
    for (const [key, value] of Object.entries(extra)) {
      if (value !== null && value !== undefined) {
        // Redact URLs
        if (key.toLowerCase().includes('url') && typeof value === 'string') {
          optionalParts.push(`${key}=${redactUrl(value)}`);
        } else {
          optionalParts.push(`${key}=${value}`);
        }
      }
    }
    if (optionalParts.length > 0) {
      parts.push('| ' + optionalParts.join(' '));
    }
  }
  
  const logMessage = parts.join(' ');
  
  // Use console.info for all structured logs (can be filtered by log aggregators)
  console.info(logMessage);
}
