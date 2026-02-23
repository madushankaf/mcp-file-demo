import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import { generateTraceId, logStructured, redactUrl } from './logging';

// Get AI service URL from environment variable (defaults to localhost:8000)
const AI_SERVICE_PORT = process.env.REACT_APP_AI_SERVICE_PORT || '8000';
const AI_SERVICE_URL = process.env.REACT_APP_AI_SERVICE_URL || `http://localhost:${AI_SERVICE_PORT}`;

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [attachedFile, setAttachedFile] = useState(null);
  const fileInputRef = useRef(null);
  const attachFileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Check service connectivity on mount
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(`${AI_SERVICE_URL}/health`);
        if (response.ok) {
          console.log('✓ AI service is reachable at', AI_SERVICE_URL);
        } else {
          console.warn('⚠ AI service health check failed:', response.status);
        }
      } catch (error) {
        console.error('✗ Cannot reach AI service at', AI_SERVICE_URL, error.message);
      }
    };
    checkHealth();
  }, []);

  const handleElicitation = async (elicitation, traceId) => {
    if (elicitation.mode === 'url') {
      logStructured(
        'UI',
        '→',
        'file_picker_open',
        `Opening file picker for URL-mode elicitation`,
        traceId,
        { url: redactUrl(elicitation.url) }
      );
      
      // Open file picker
      fileInputRef.current?.click();
      
      // Store elicitation data for when file is selected
      fileInputRef.current.dataset.url = elicitation.url;
      fileInputRef.current.dataset.message = elicitation.message;
      fileInputRef.current.dataset.uploadMode = 'ui'; // Mark as UI mode
      fileInputRef.current.dataset.traceId = traceId;
    }
  };

  const handleStreamUpload = async (streamData, traceId) => {
    logStructured(
      'UI',
      '→',
      'file_picker_open',
      `Opening file picker for stream upload`,
      traceId,
      { url: redactUrl(streamData.url) }
    );
    
    // Open file picker for direct upload
    fileInputRef.current?.click();
    
    // Store stream data for when file is selected
    fileInputRef.current.dataset.url = streamData.url;
    fileInputRef.current.dataset.message = streamData.message;
    fileInputRef.current.dataset.uploadMode = 'stream'; // Mark as stream mode
    fileInputRef.current.dataset.traceId = traceId;
  };

  const handleFileSelect = async (event) => {
    const file = event.target.files[0];
    if (!file) {
      return;
    }

    const url = event.target.dataset.url;
    const message = event.target.dataset.message;
    const uploadMode = event.target.dataset.uploadMode || 'ui';
    const traceId = event.target.dataset.traceId || generateTraceId();
    const fileSize = `${(file.size / 1024).toFixed(2)} KB`;

    logStructured(
      'UI',
      '→',
      'file_selected',
      `File selected: ${file.name} (${fileSize})`,
      traceId,
      { file_name: file.name, file_size: fileSize, upload_mode: uploadMode }
    );

    // Add user message about file selection
    setMessages(prev => [...prev, {
      type: 'user',
      text: `Selected file: ${file.name}`
    }]);

    setIsProcessing(true);

    try {
      const uploadStartTime = Date.now();
      
      logStructured(
        'UI',
        '→',
        'file_upload_start',
        `Starting multipart file upload to File API`,
        traceId,
        { file_name: file.name, url: redactUrl(url), upload_mode: uploadMode }
      );
      
      // POST file directly to the file-api URL
      const formData = new FormData();
      formData.append('file', file);

      const uploadResponse = await fetch(url, {
        method: 'POST',
        headers: {
          'X-Trace-ID': traceId
        },
        body: formData
      });

      const uploadDurationMs = Date.now() - uploadStartTime;

      if (!uploadResponse.ok) {
        throw new Error('File upload failed');
      }

      const uploadResult = await uploadResponse.json();
      
      logStructured(
        'UI',
        '←',
        'file_upload_complete',
        `File upload successful`,
        traceId,
        { file_id: uploadResult.file_id, status_code: uploadResponse.status, duration_ms: uploadDurationMs }
      );
      
      // Add success message
      const successMessage = uploadMode === 'stream' 
        ? `File streamed directly to API! File ID: ${uploadResult.file_id}`
        : `File uploaded successfully! File ID: ${uploadResult.file_id}`;
      
      setMessages(prev => [...prev, {
        type: 'assistant',
        text: successMessage
      }]);

      // Only send completion notification for UI mode (elicitation flow)
      if (uploadMode === 'ui') {
        const completeUrl = `${AI_SERVICE_URL}/elicitation/complete`;
        logStructured(
          'UI',
          '→',
          'elicitation_complete_notify',
          `Notifying AI service of elicitation completion`,
          traceId,
          { file_id: uploadResult.file_id }
        );
        
        await fetch(completeUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Trace-ID': traceId
          },
          body: JSON.stringify({
            status: 'success',
            file_id: uploadResult.file_id
          })
        });
      }

    } catch (error) {
      console.error('❌ [UPLOAD] Error uploading file:', error);
      setMessages(prev => [...prev, {
        type: 'error',
        text: `Error uploading file: ${error.message}`
      }]);
    } finally {
      setIsProcessing(false);
      // Reset file input
      event.target.value = '';
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || isProcessing) return;

    const traceId = generateTraceId();
    const userMessage = input.trim();
    const hasFile = attachedFile !== null;
    const fileName = attachedFile ? attachedFile.name : null;
    const fileSize = attachedFile ? `${(attachedFile.size / 1024).toFixed(2)} KB` : null;
    
    logStructured(
      'UI',
      '→',
      'user_message',
      `User message: ${userMessage.substring(0, 100)}${userMessage.length > 100 ? '...' : ''}`,
      traceId,
      { file_attached: hasFile, file_name: fileName, file_size: fileSize }
    );
    
    // Show user message with file indicator if file is attached
    const messageText = attachedFile 
      ? `${userMessage} [File attached: ${attachedFile.name}]`
      : userMessage;
    
    setInput('');
    setMessages(prev => [...prev, { type: 'user', text: messageText }]);
    setIsProcessing(true);

    try {
      const chatUrl = `${AI_SERVICE_URL}/chat`;
      const startTime = Date.now();
      
      logStructured(
        'UI',
        '→',
        'chat_request',
        `Sending chat request to AI service`,
        traceId,
        { url: redactUrl(chatUrl), file_attached: hasFile }
      );
      
      // ALWAYS send JSON only - never send file data to AI service
      // But include file attachment status so AI service knows if file is ready
      const response = await fetch(chatUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Trace-ID': traceId
        },
        body: JSON.stringify({ 
          message: userMessage,
          has_attached_file: attachedFile !== null
        })
      });
      
      const durationMs = Date.now() - startTime;

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      
      logStructured(
        'UI',
        '←',
        'chat_response',
        `Received chat response from AI service`,
        traceId,
        { status_code: response.status, duration_ms: durationMs, has_elicitation: !!data.elicitation }
      );
      
      setMessages(prev => [...prev, {
        type: 'assistant',
        text: data.response
      }]);

      // Check if there's an elicitation request (UI mode) or stream upload request
      if (data.elicitation) {
        if (data.elicitation.type === 'elicitation' && data.elicitation.mode === 'url') {
          logStructured(
            'UI',
            '←',
            'elicitation_received',
            `Received URL-mode elicitation`,
            traceId,
            { mode: 'url', url: redactUrl(data.elicitation.url) }
          );
          // Handle the elicitation (UI mode) - opens file picker
          await handleElicitation(data.elicitation, traceId);
        } else if (data.elicitation.type === 'stream_upload' && data.elicitation.mode === 'stream') {
          logStructured(
            'UI',
            '←',
            'stream_url_received',
            `Received stream upload URL`,
            traceId,
            { mode: 'stream', url: redactUrl(data.elicitation.url) }
          );
          // If file is already attached, upload it directly to the stream URL
          if (attachedFile) {
            logStructured(
              'UI',
              '→',
              'auto_upload_start',
              `File attached, starting automatic upload`,
              traceId,
              { file_name: attachedFile.name }
            );
            await uploadFileToStreamUrl(attachedFile, data.elicitation, traceId);
            // Clear attached file after successful upload
            setAttachedFile(null);
          } else {
            // No file attached, open file picker
            await handleStreamUpload(data.elicitation, traceId);
          }
        }
      }

    } catch (error) {
      logStructured(
        'UI',
        '←',
        'chat_error',
        `Chat request failed: ${error.message}`,
        traceId
      );
      
      let errorMessage = `Error: ${error.message}`;
      
      // Provide helpful error messages
      if (error.message.includes('Failed to fetch') || error.message.includes('ERR_CONNECTION_REFUSED')) {
        errorMessage = `Connection refused. Is the ai-service running on ${AI_SERVICE_URL}?`;
      } else if (error.message.includes('404')) {
        errorMessage = `Endpoint not found. Check if ai-service is running and the URL is correct: ${AI_SERVICE_URL}`;
      }
      
      setMessages(prev => [...prev, {
        type: 'error',
        text: errorMessage
      }]);
    } finally {
      setIsProcessing(false);
    }
  };

  const uploadFileToStreamUrl = async (file, streamData) => {
    console.log('🌊 [STREAM UPLOAD] Uploading file directly to stream URL:', streamData.url);
    console.log('📁 [STREAM UPLOAD] File:', file.name, `(${(file.size / 1024).toFixed(2)} KB)`);
    
    setIsProcessing(true);
    
    try {
      const formData = new FormData();
      formData.append('file', file);

      const uploadResponse = await fetch(streamData.url, {
        method: 'POST',
        body: formData
      });

      if (!uploadResponse.ok) {
        throw new Error('File upload failed');
      }

      const uploadResult = await uploadResponse.json();
      console.log('✅ [STREAM UPLOAD] File uploaded successfully:', uploadResult);
      
      setMessages(prev => [...prev, {
        type: 'assistant',
        text: `File streamed successfully! File ID: ${uploadResult.file_id}`
      }]);

    } catch (error) {
      console.error('❌ [STREAM UPLOAD] Error uploading file:', error);
      setMessages(prev => [...prev, {
        type: 'error',
        text: `Error uploading file: ${error.message}`
      }]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleAttachFile = () => {
    attachFileInputRef.current?.click();
  };

  const handleAttachFileSelect = (event) => {
    const file = event.target.files[0];
    if (file) {
      console.log('📎 [ATTACH] File attached:', file.name, `(${(file.size / 1024).toFixed(2)} KB)`);
      setAttachedFile(file);
      setMessages(prev => [...prev, {
        type: 'system',
        text: `📎 Attached: ${file.name}`
      }]);
    }
    // Reset input so same file can be selected again
    event.target.value = '';
  };

  const removeAttachedFile = () => {
    console.log('🗑️ [ATTACH] Removing attached file');
    setAttachedFile(null);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="App">
      <div className="chat-container">
        <div className="chat-header">
          <h1>MCP File Upload Demo</h1>
        </div>
        <div className="messages">
          {messages.length === 0 && (
            <div className="message assistant">
              <div className="message-content">
                Welcome! Type "process file" or "upload file" to start.
              </div>
            </div>
          )}
          {messages.map((msg, idx) => (
            <div key={idx} className={`message ${msg.type}`}>
              <div className="message-content">
                {msg.text}
              </div>
            </div>
          ))}
          {isProcessing && (
            <div className="message assistant">
              <div className="message-content">Processing...</div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
        <div className="input-area">
          {attachedFile && (
            <div className="attached-file">
              <span>📎 {attachedFile.name}</span>
              <button onClick={removeAttachedFile} className="remove-file">×</button>
            </div>
          )}
          <div className="input-area-row">
            <button 
              onClick={handleAttachFile} 
              className="attach-button"
              disabled={isProcessing}
              title="Attach file"
            >
              +
            </button>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type a message..."
              disabled={isProcessing}
            />
            <button onClick={sendMessage} disabled={isProcessing || !input.trim()}>
              Send
            </button>
          </div>
        </div>
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          onChange={handleFileSelect}
        />
        <input
          type="file"
          ref={attachFileInputRef}
          style={{ display: 'none' }}
          onChange={handleAttachFileSelect}
        />
      </div>
    </div>
  );
}

export default App;
