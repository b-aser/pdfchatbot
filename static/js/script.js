document.addEventListener("DOMContentLoaded", function () {
  const uploadForm = document.getElementById("uploadForm");
  const chatForm = document.getElementById("chatForm");
  const documentList = document.getElementById("documentList");
  const chatMessages = document.getElementById("chatMessages");
  const userInput = document.getElementById("userInput");

  let uploadedDocuments = [];

  // Handle PDF uploads
  uploadForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const files = document.getElementById("pdfFiles").files;
    if (files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }

    fetch("/upload", {
      method: "POST",
      body: formData,
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.files) {
          updateDocumentList(data.files);
          addBotMessage(
            `I've processed ${data.files.length} document(s). You can now ask questions about them.`
          );
        }
      })
      .catch((error) => {
        console.error("Error:", error);
        addBotMessage("Sorry, there was an error processing your documents.");
      });
  });

  // Handle chat questions
  chatForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const question = userInput.value.trim();
    if (!question) return;

    addUserMessage(question);
    userInput.value = "";

    // Get selected documents
    const selectedDocs = Array.from(
      document.querySelectorAll(".document-item.active")
    ).map((item) => item.dataset.filename);

    if (selectedDocs.length === 0 && uploadedDocuments.length > 0) {
      addBotMessage(
        "Please select which documents you want to ask about from the sidebar."
      );
      return;
    }

    fetch("/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question: question,
        documents: selectedDocs.length > 0 ? selectedDocs : uploadedDocuments,
      }),
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.answer) {
          addBotMessage(data.answer, data.sources);
        }
      })
      .catch((error) => {
        console.error("Error:", error);
        addBotMessage("Sorry, there was an error processing your question.");
      });
  });

  // Update document list in sidebar
  function updateDocumentList(files) {
    documentList.innerHTML = "";
    uploadedDocuments = [];

    files.forEach((file) => {
      if (file.status === "processed") {
        uploadedDocuments.push(file.filename);

        const docItem = document.createElement("div");
        docItem.className =
          "list-group-item document-item d-flex justify-content-between align-items-center";
        docItem.dataset.filename = file.filename;

        docItem.innerHTML = `
                    <div>
                        <input class="form-check-input me-2" type="checkbox" checked>
                        ${file.filename}
                    </div>
                    <span class="badge bg-primary rounded-pill">new</span>
                `;

        // Toggle document selection
        docItem.addEventListener("click", function (e) {
          if (e.target.type !== "checkbox") {
            const checkbox = this.querySelector(".form-check-input");
            checkbox.checked = !checkbox.checked;
          }
          this.classList.toggle(
            "active",
            this.querySelector(".form-check-input").checked
          );
        });

        documentList.appendChild(docItem);
      }
    });
  }

  // Add user message to chat
  function addUserMessage(message) {
    const messageDiv = document.createElement("div");
    messageDiv.className = "chat-message user-message";
    messageDiv.textContent = message;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
  }

  // Add bot message to chat
  function addBotMessage(message, sources = []) {
    const messageDiv = document.createElement("div");
    messageDiv.className = "chat-message bot-message mb-3";

    let sourcesHTML = "";
    if (sources && sources.length > 0) {
      sourcesHTML = `<div class="mt-2"><small>Sources: `;
      sourcesHTML += sources
        .map(
          (src) => `<span class="badge bg-secondary source-badge">${src}</span>`
        )
        .join("");
      sourcesHTML += `</small></div>`;
    }

    messageDiv.innerHTML = `<div>${message}</div>${sourcesHTML}`;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
  }

  // Scroll chat to bottom
  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
});
