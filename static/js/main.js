const form = document.getElementById("qr-form");
const previewImage = document.getElementById("qr-preview");
const previewMessage = document.getElementById("preview-message");
const errorTemplate = document.getElementById("error-template");

let previewTimeout;

const ERROR_MESSAGES = {
  network: "サーバーとの通信に失敗しました。時間をおいて再度お試しください。",
};

function showError(message) {
  const clone = errorTemplate.content.cloneNode(true);
  const dialog = clone.querySelector("dialog");
  const messageElement = clone.querySelector(".error-message");
  const closeButton = clone.querySelector(".close-dialog");

  dialog.classList.add("error-dialog");
  messageElement.textContent = message;
  document.body.appendChild(dialog);

  const closeDialog = () => {
    dialog.close();
    dialog.remove();
  };

  closeButton.addEventListener("click", closeDialog, { once: true });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      closeDialog();
    }
  });
}

function buildRequestPayload() {
  const formData = new FormData(form);
  return {
    data: formData.get("data") ?? "",
    errorCorrection: formData.get("errorCorrection") ?? "M",
    border: formData.get("border") ?? 4,
    moduleSize: formData.get("moduleSize") ?? 1,
  };
}

async function updatePreview() {
  const payload = buildRequestPayload();
  const params = new URLSearchParams(payload);

  if (!payload.data.trim()) {
    previewImage.src = "";
    previewImage.hidden = true;
    previewMessage.textContent = "テキストを入力するとプレビューが表示されます。";
    return;
  }

  previewMessage.textContent = "プレビューを生成しています…";

  try {
    const response = await fetch(`/api/qr-preview?${params.toString()}`, {
      headers: {
        "Accept": "image/png",
      },
    });

    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.message || "プレビューの生成に失敗しました。");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    previewImage.src = url;
    previewImage.hidden = false;
    previewMessage.textContent = "";
  } catch (error) {
    previewImage.src = "";
    previewImage.hidden = true;
    previewMessage.textContent = error.message || ERROR_MESSAGES.network;
  }
}

form.addEventListener("input", () => {
  clearTimeout(previewTimeout);
  previewTimeout = setTimeout(updatePreview, 350);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = buildRequestPayload();

  if (!payload.data.trim()) {
    showError("テキストを入力してください。");
    return;
  }

  try {
    const response = await fetch("/api/qr-dxf", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.message || "DXFの生成に失敗しました。");
    }

    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition");
    let filename = "qr_code.dxf";
    if (disposition) {
      const match = /filename="?([^";]+)"?/i.exec(disposition);
      if (match) {
        filename = decodeURIComponent(match[1]);
      }
    }

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    showError(error.message || ERROR_MESSAGES.network);
  }
});

window.addEventListener("DOMContentLoaded", () => {
  updatePreview();
});
