/**
 * OpenFileRescue - Frontend Application Logic
 * Real-time sector mapping, file carving streaming, preview lightbox, and free export.
 */

// Application State
const state = {
  sources: [],
  selectedSourcePath: "",
  isScanning: false,
  isPaused: false,
  pollTimer: null,
  files: [],
  selectedFileIds: new Set(),
  activeFilter: "all",
  activeFileForLightbox: null,
  gridBlockCount: 120
};

// DOM Elements
const elements = {
  sourceSelect: document.getElementById("source-select"),
  customPathInput: document.getElementById("custom-path-input"),
  stepSelect: document.getElementById("step-select"),
  btnStart: document.getElementById("btn-start-scan"),
  btnPause: document.getElementById("btn-pause-scan"),
  btnStop: document.getElementById("btn-stop-scan"),
  btnCreateSample: document.getElementById("btn-create-sample"),
  btnRefreshSources: document.getElementById("btn-refresh-sources"),

  // Telemetry
  statProgress: document.getElementById("stat-progress"),
  progressBarFill: document.getElementById("progress-bar-fill"),
  statScanned: document.getElementById("stat-scanned"),
  statSpeed: document.getElementById("stat-speed"),
  statFilesFound: document.getElementById("stat-files-found"),
  statFileBreakdown: document.getElementById("stat-file-breakdown"),
  statEta: document.getElementById("stat-eta"),
  statStatusMsg: document.getElementById("stat-status-msg"),
  statBadSectors: document.getElementById("stat-bad-sectors"),

  // Sector Map
  sectorGrid: document.getElementById("sector-grid"),

  // Gallery
  galleryTabs: document.getElementById("gallery-tabs"),
  photoGrid: document.getElementById("photo-grid"),
  emptyState: document.getElementById("empty-state"),
  selectAllCheckbox: document.getElementById("select-all-checkbox"),
  btnOpenExport: document.getElementById("btn-open-export"),
  exportCountBadge: document.getElementById("export-count-badge"),
  countAll: document.getElementById("count-all"),
  countJpg: document.getElementById("count-jpg"),
  countPng: document.getElementById("count-png"),
  countRaw: document.getElementById("count-raw"),
  countVideo: document.getElementById("count-video"),

  // Modals
  exportModal: document.getElementById("export-modal"),
  exportDirInput: document.getElementById("export-dir-input"),
  exportOrgSelect: document.getElementById("export-org-select"),
  btnCloseExport: document.getElementById("btn-close-export"),
  btnCancelExport: document.getElementById("btn-cancel-export"),
  btnConfirmExport: document.getElementById("btn-confirm-export"),
  exportSummaryText: document.getElementById("export-summary-text"),

  lightboxModal: document.getElementById("lightbox-modal"),
  lightboxImg: document.getElementById("lightbox-img"),
  lightboxTitle: document.getElementById("lightbox-title"),
  lightboxMeta: document.getElementById("lightbox-meta"),
  lightboxDownloadBtn: document.getElementById("lightbox-download-btn"),
  btnCloseLightbox: document.getElementById("btn-close-lightbox"),

  toastContainer: document.getElementById("toast-container")
};

// Utilities
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function formatBytes(bytes) {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(2)} ${units[i]}`;
}

function formatDuration(sec) {
  if (sec <= 0 || !isFinite(sec)) return "--:--";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

// Initialize Sector Grid DOM
function initSectorGrid() {
  elements.sectorGrid.innerHTML = "";
  for (let i = 0; i < state.gridBlockCount; i++) {
    const block = document.createElement("div");
    block.className = "sector-block block-pending";
    block.id = `block-${i}`;
    block.title = `LBA Block #${i + 1}`;
    elements.sectorGrid.appendChild(block);
  }
}

// Update Sector Grid from Carver Status
function updateSectorGrid(mapArray) {
  if (!mapArray || !mapArray.length) return;
  const classes = ["block-pending", "block-scanned", "block-found", "block-bad"];
  for (let i = 0; i < mapArray.length && i < state.gridBlockCount; i++) {
    const el = document.getElementById(`block-${i}`);
    if (el) {
      const stateIdx = mapArray[i] || 0;
      el.className = `sector-block ${classes[stateIdx] || "block-pending"}`;
    }
  }
}

// Fetch Available Drives and Disks
async function loadSources() {
  try {
    const res = await fetch("/api/sources");
    const json = await res.json();
    if (json.success) {
      state.sources = json.sources;
      renderSourceOptions();
    }
  } catch (err) {
    showToast("Unable to connect to local server.", "error");
  }
}

function renderSourceOptions() {
  elements.sourceSelect.innerHTML = "";
  if (!state.sources.length) {
    elements.sourceSelect.innerHTML = '<option value="">No drives found (enter path or create demo SD image)</option>';
    return;
  }

  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "-- Select drive or disk image to scan --";
  elements.sourceSelect.appendChild(defaultOpt);

  state.sources.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.path;
    opt.textContent = `${s.name} [${s.size_formatted}] (${s.filesystem})`;
    elements.sourceSelect.appendChild(opt);
  });

  // Auto-select if a removable SD card or demo image is present
  const sd = state.sources.find((s) => s.path.includes("Kids Camera") || s.path.includes("sample_microsd") || s.type === "drive_volume");
  if (sd) {
    elements.sourceSelect.value = sd.path;
    state.selectedSourcePath = sd.path;
  }
}

// Scan Actions
async function startScan() {
  const custom = elements.customPathInput.value.trim();
  const source = custom || elements.sourceSelect.value;
  if (!source) {
    showToast("Please select a drive or enter a valid path first.", "error");
    return;
  }

  state.selectedSourcePath = source;
  const step = parseInt(elements.stepSelect.value, 10) || 512;

  try {
    const res = await fetch("/api/scan/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_path: source, sector_step: step })
    });
    const json = await res.json();
    if (json.success) {
      showToast("Scan started in safe Read-Only mode!", "success");
      state.isScanning = true;
      state.isPaused = false;
      state.files = [];
      state.selectedFileIds.clear();
      updateUIControls();
      initSectorGrid();
      startPolling();
    } else {
      showToast(`Error: ${json.error}`, "error");
    }
  } catch (err) {
    showToast(`Failed to start scan: ${err}`, "error");
  }
}

async function pauseScan() {
  try {
    const res = await fetch("/api/scan/pause", { method: "POST" });
    const json = await res.json();
    if (json.success) {
      state.isPaused = true;
      updateUIControls();
      showToast("Scan paused.", "info");
    }
  } catch (err) {}
}

async function resumeScan() {
  try {
    const res = await fetch("/api/scan/resume", { method: "POST" });
    const json = await res.json();
    if (json.success) {
      state.isPaused = false;
      updateUIControls();
      showToast("Scan resumed.", "info");
    }
  } catch (err) {}
}

async function stopScan() {
  try {
    const res = await fetch("/api/scan/stop", { method: "POST" });
    const json = await res.json();
    if (json.success) {
      state.isScanning = false;
      state.isPaused = false;
      stopPolling();
      updateUIControls();
      showToast("Scan stopped.", "info");
      pollFiles(); // Final fetch
    }
  } catch (err) {}
}

function updateUIControls() {
  elements.btnStart.disabled = state.isScanning && !state.isPaused;
  elements.btnPause.disabled = !state.isScanning;
  elements.btnPause.textContent = state.isPaused ? "Resume" : "Pause";
  elements.btnStop.disabled = !state.isScanning;
}

// Telemetry Polling
function startPolling() {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    await pollStatus();
    await pollFiles();
  }, 400);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function pollStatus() {
  try {
    const res = await fetch("/api/scan/status");
    const json = await res.json();
    if (!json.success) return;

    // Update Progress
    elements.statProgress.textContent = `${json.percent.toFixed(1)}%`;
    elements.progressBarFill.style.width = `${json.percent}%`;

    // Scanned Bytes & Speed
    elements.statScanned.textContent = `${formatBytes(json.scanned_bytes)} / ${formatBytes(json.total_bytes)}`;
    elements.statSpeed.textContent = `Speed: ${(json.bytes_per_second / (1024 * 1024)).toFixed(1)} MB/s`;

    // Files Found Breakdown
    elements.statFilesFound.textContent = json.files_found;
    const types = json.file_counts_by_type || {};
    const parts = Object.entries(types).map(([k, v]) => `${v} ${k}`);
    elements.statFileBreakdown.textContent = parts.length ? parts.join(", ") : "Scanning storage...";

    // ETA & Status
    elements.statEta.textContent = formatDuration(json.eta_seconds);
    elements.statStatusMsg.textContent = json.status_message;

    // Bad sectors
    elements.statBadSectors.textContent = json.bad_sectors_count;

    // Update Sector Visualizer
    updateSectorGrid(json.sector_map);

    if (json.is_finished) {
      state.isScanning = false;
      stopPolling();
      updateUIControls();
      showToast("Scan completed successfully!", "success");
      await pollFiles();
    }
  } catch (err) {}
}

async function pollFiles() {
  try {
    const res = await fetch("/api/files");
    const json = await res.json();
    if (json.success && json.files) {
      if (json.files.length !== state.files.length) {
        state.files = json.files;
        renderGallery();
      }
    }
  } catch (err) {}
}

// Gallery & Filtering
function renderGallery() {
  const photoExts = [".jpg", ".jpeg", ".png", ".cr2", ".nef", ".arw", ".dng", ".raf"];
  const videoExts = [".mp4", ".mov", ".avi", ".3gp", ".m4v"];
  const audioExts = [".mp3", ".wav"];
  const docExts = [".pdf", ".zip", ".docx", ".xlsx", ".pptx", ".apk"];

  const filtered = state.files.filter((f) => {
    const ext = (f.extension || "").toLowerCase();
    if (state.activeFilter === "all") return true;
    if (state.activeFilter === "photos") return photoExts.includes(ext);
    if (state.activeFilter === "video") return videoExts.includes(ext);
    if (state.activeFilter === "audio") return audioExts.includes(ext);
    if (state.activeFilter === "docs") return docExts.includes(ext);
    return true;
  });

  // Update counts
  if (elements.countAll) elements.countAll.textContent = state.files.length;
  const countPhotosEl = document.getElementById("count-photos");
  const countVideoEl = document.getElementById("count-video");
  const countAudioEl = document.getElementById("count-audio");
  const countDocsEl = document.getElementById("count-docs");

  if (countPhotosEl) countPhotosEl.textContent = state.files.filter((f) => photoExts.includes((f.extension||"").toLowerCase())).length;
  if (countVideoEl) countVideoEl.textContent = state.files.filter((f) => videoExts.includes((f.extension||"").toLowerCase())).length;
  if (countAudioEl) countAudioEl.textContent = state.files.filter((f) => audioExts.includes((f.extension||"").toLowerCase())).length;
  if (countDocsEl) countDocsEl.textContent = state.files.filter((f) => docExts.includes((f.extension||"").toLowerCase())).length;

  if (state.files.length === 0) {
    elements.emptyState.style.display = "flex";
    elements.photoGrid.style.display = "none";
    return;
  }

  elements.emptyState.style.display = "none";
  elements.photoGrid.style.display = "grid";
  elements.photoGrid.innerHTML = "";

  filtered.forEach((file) => {
    const card = document.createElement("div");
    card.className = "photo-card";

    const isSelected = state.selectedFileIds.has(file.id);
    const extClass = `badge-${file.extension.replace(".", "").toLowerCase()}`;

    // Thumbnail src
    let thumbSrc = file.thumbnail || `/api/file/${file.id}/preview`;

    card.innerHTML = `
      <input type="checkbox" class="card-select" data-id="${file.id}" ${isSelected ? "checked" : ""}>
      <div class="photo-thumb-wrap" data-id="${file.id}">
        <img src="${thumbSrc}" alt="${file.id}" loading="lazy" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100\\' height=\\'100\\' fill=\\'%23666\\'><rect width=\\'100\\' height=\\'100\\' fill=\\'%23111\\'/><text x=\\'50%\\' y=\\'50%\\' fill=\\'%23999\\' dominant-baseline=\\'middle\\' text-anchor=\\'middle\\'>File</text></svg>'">
        <span class="file-type-badge ${extClass}">${file.extension.replace(".", "")}</span>
      </div>
      <div class="card-body">
        <div class="card-name" title="${file.id}">${file.id}${file.extension}</div>
        <div class="card-meta-row">
          <span>${formatBytes(file.size)}</span>
          <span>Sector: 0x${file.offset.toString(16).toUpperCase()}</span>
        </div>
        ${file.metadata && file.metadata.camera_make ? `<div class="card-camera">${file.metadata.camera_make} ${file.metadata.camera_model || ""}</div>` : ""}
      </div>
    `;

    // Checkbox toggle
    const chk = card.querySelector(".card-select");
    chk.addEventListener("change", (e) => {
      e.stopPropagation();
      if (chk.checked) {
        state.selectedFileIds.add(file.id);
      } else {
        state.selectedFileIds.delete(file.id);
      }
      updateExportBadge();
    });

    // Lightbox open on thumbnail click
    const thumbWrap = card.querySelector(".photo-thumb-wrap");
    thumbWrap.addEventListener("click", () => openLightbox(file));

    elements.photoGrid.appendChild(card);
  });

  updateExportBadge();
}

function updateExportBadge() {
  const count = state.selectedFileIds.size > 0 ? state.selectedFileIds.size : state.files.length;
  elements.exportCountBadge.textContent = count;
  elements.selectAllCheckbox.checked = state.files.length > 0 && state.selectedFileIds.size === state.files.length;
}

// Lightbox Modal
function openLightbox(file) {
  state.activeFileForLightbox = file;
  elements.lightboxTitle.textContent = `${file.id}${file.extension}`;
  elements.lightboxImg.src = `/api/file/${file.id}/preview`;
  elements.lightboxDownloadBtn.href = `/api/file/${file.id}/preview`;
  elements.lightboxDownloadBtn.download = `recovered_${file.id}${file.extension}`;

  elements.lightboxMeta.innerHTML = `
    <div class="meta-row"><span class="meta-key">Format:</span><span class="meta-val">${file.parser_name}</span></div>
    <div class="meta-row"><span class="meta-key">File Size:</span><span class="meta-val">${formatBytes(file.size)}</span></div>
    <div class="meta-row"><span class="meta-key">LBA Offset:</span><span class="meta-val">0x${file.offset.toString(16).toUpperCase()}</span></div>
    <div class="meta-row"><span class="meta-key">Integrity:</span><span class="meta-val" style="color: #34d399;">${file.integrity}</span></div>
    ${file.metadata && file.metadata.camera_make ? `<div class="meta-row"><span class="meta-key">Camera:</span><span class="meta-val">${file.metadata.camera_make}</span></div>` : ""}
    ${file.metadata && file.metadata.camera_model ? `<div class="meta-row"><span class="meta-key">Model:</span><span class="meta-val">${file.metadata.camera_model}</span></div>` : ""}
    ${file.metadata && file.metadata.date_taken ? `<div class="meta-row"><span class="meta-key">Date Taken:</span><span class="meta-val">${file.metadata.date_taken}</span></div>` : ""}
    ${file.metadata && file.metadata.width ? `<div class="meta-row"><span class="meta-key">Dimensions:</span><span class="meta-val">${file.metadata.width} x ${file.metadata.height}</span></div>` : ""}
  `;

  elements.lightboxModal.style.display = "flex";
}

function closeLightbox() {
  elements.lightboxModal.style.display = "none";
  elements.lightboxImg.src = "";
}

// Export Dialog
function openExportModal() {
  if (state.files.length === 0) {
    showToast("No recovered files to export.", "error");
    return;
  }
  const count = state.selectedFileIds.size > 0 ? state.selectedFileIds.size : state.files.length;
  elements.exportSummaryText.textContent = `Ready to export ${count} selected files. Recovery is 100% free with no MB limits or paywalls!`;
  elements.exportModal.style.display = "flex";
}

function closeExportModal() {
  elements.exportModal.style.display = "none";
}

async function confirmExport() {
  const dir = elements.exportDirInput.value.trim();
  const org = elements.exportOrgSelect.value;
  const fileIds = Array.from(state.selectedFileIds);

  try {
    const res = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_dir: dir,
        organization: org,
        file_ids: fileIds
      })
    });
    const json = await res.json();
    if (json.success) {
      closeExportModal();
      showToast(`Successfully exported ${json.summary.total_exported} files (${formatBytes(json.summary.total_bytes)}) to: ${json.summary.output_directory}`, "success");
    } else {
      showToast(`Export failed: ${json.error}`, "error");
    }
  } catch (err) {
    showToast(`Export error: ${err}`, "error");
  }
}

// Create Test Sample SD Image
async function createSampleSD() {
  elements.btnCreateSample.disabled = true;
  elements.btnCreateSample.textContent = "Creating demo image...";
  try {
    const res = await fetch("/api/create_sample_disk", { method: "POST" });
    const json = await res.json();
    if (json.success) {
      showToast("Demo SD card created with simulated photos!", "success");
      await loadSources();
      elements.customPathInput.value = json.image_path;
      state.selectedSourcePath = json.image_path;
    }
  } catch (err) {
    showToast("Failed to create demo test image", "error");
  } finally {
    elements.btnCreateSample.disabled = false;
    elements.btnCreateSample.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
        <line x1="12" y1="8" x2="12" y2="16"></line>
        <line x1="8" y1="12" x2="16" y2="12"></line>
      </svg>
      Create Demo SD Image
    `;
  }
}

// Event Listeners
function setupEventListeners() {
  elements.sourceSelect.addEventListener("change", (e) => {
    state.selectedSourcePath = e.target.value;
    if (e.target.value) elements.customPathInput.value = "";
  });

  elements.customPathInput.addEventListener("input", (e) => {
    state.selectedSourcePath = e.target.value;
    if (e.target.value) elements.sourceSelect.value = "";
  });

  elements.btnStart.addEventListener("click", () => {
    if (state.isPaused) resumeScan();
    else startScan();
  });

  elements.btnPause.addEventListener("click", () => {
    if (state.isPaused) resumeScan();
    else pauseScan();
  });

  elements.btnStop.addEventListener("click", stopScan);
  elements.btnRefreshSources.addEventListener("click", loadSources);
  elements.btnCreateSample.addEventListener("click", createSampleSD);

  // Gallery tabs
  elements.galleryTabs.addEventListener("click", (e) => {
    const tab = e.target.closest(".tab-btn");
    if (!tab) return;
    document.querySelectorAll(".tab-btn").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    state.activeFilter = tab.dataset.filter;
    renderGallery();
  });

  // Select all checkbox
  elements.selectAllCheckbox.addEventListener("change", (e) => {
    if (e.target.checked) {
      state.files.forEach((f) => state.selectedFileIds.add(f.id));
    } else {
      state.selectedFileIds.clear();
    }
    renderGallery();
  });

  // Export Modal
  elements.btnOpenExport.addEventListener("click", openExportModal);
  elements.btnCloseExport.addEventListener("click", closeExportModal);
  elements.btnCancelExport.addEventListener("click", closeExportModal);
  elements.btnConfirmExport.addEventListener("click", confirmExport);

  // Lightbox
  elements.btnCloseLightbox.addEventListener("click", closeLightbox);
  elements.lightboxModal.addEventListener("click", (e) => {
    if (e.target === elements.lightboxModal) closeLightbox();
  });

  // Escape key closes modals
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeLightbox();
      closeExportModal();
    }
  });
}

// Boot
document.addEventListener("DOMContentLoaded", () => {
  initSectorGrid();
  setupEventListeners();
  loadSources();
});
