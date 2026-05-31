import { useState } from 'react';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");

  // Handle Drag and Drop
  const handleDrop = (e) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    validateAndSetFile(droppedFile);
  };

  const handleDragOver = (e) => {
    e.preventDefault(); // Required to allow dropping
  };

  // Handle manual file selection
  const handleFileChange = (e) => {
    validateAndSetFile(e.target.files[0]);
  };

  const validateAndSetFile = (selectedFile) => {
    if (selectedFile && selectedFile.name.match(/\.(cpp|c|cc|cxx)$/)) {
      setFile(selectedFile);
      setStatusMsg("");
    } else {
      setFile(null);
      setStatusMsg("⚠️ Please upload a valid C++ file (.cpp, .c, .cc)");
    }
  };

  // Connect to FastAPI Backend
  const handleOptimize = async () => {
    if (!file) return;
    
    setIsOptimizing(true);
    setStatusMsg("🤖 AI is analyzing and compiling... This usually takes 30-60 seconds.");

    const formData = new FormData();
    formData.append("cpp_files", file);
    // Passing empty strings for optional args to satisfy the backend form requirements
    formData.append("program_args", "");
    formData.append("include_dirs", "");
    formData.append("skip_execution", false);

    try {
      const response = await fetch("http://localhost:8000/optimize-files", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server Error: ${response.status}`);
      }

      // Convert binary response to a downloadable file
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `optimized_${file.name}`;
      document.body.appendChild(link);
      link.click();
      
      // Cleanup
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      setStatusMsg("✅ Optimization complete! Your file has been downloaded.");
    } catch (error) {
      console.error(error);
      setStatusMsg(`❌ Error: ${error.message}`);
    } finally {
      setIsOptimizing(false);
    }
  };

  return (
    <div className="container">
      <header>
        <h1>C++ AI Optimizer</h1>
        <p>Drop a raw C++ file here to run it through the reinforcement loop.</p>
      </header>

      <div 
        className={`drop-zone ${isOptimizing ? 'disabled' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        <p>Drag & Drop your .cpp file here</p>
        <p className="or-text">- or -</p>
        <input 
          type="file" 
          accept=".cpp,.c,.cc,.cxx" 
          onChange={handleFileChange} 
          disabled={isOptimizing}
          id="file-upload"
        />
      </div>

      {file && (
        <div className="file-info">
          <p><strong>Selected File:</strong> {file.name}</p>
          <button 
            onClick={handleOptimize} 
            disabled={isOptimizing}
            className={isOptimizing ? 'btn-optimizing' : 'btn-primary'}
          >
            {isOptimizing ? 'Optimizing (Please Wait)...' : 'Optimize Code'}
          </button>
        </div>
      )}

      {statusMsg && (
        <div className={`status-message ${statusMsg.includes('❌') ? 'error' : ''}`}>
          {statusMsg}
        </div>
      )}
    </div>
  );
}

export default App;