// =====================================================
// GLOBAL APP STATE
// =====================================================

const EVENT_SETS = {
  indoorDay: {
    label: "Indoor Day",
    count: 20
  },
  outdoorDay: {
    label: "Outdoor Day",
    count: 25
  },
  indoorNight: {
    label: "Indoor Night",
    count: 20
  },
  outdoorNight: {
    label: "Outdoor Night",
    count: 25
  }
};

const INDOOR_EVENT_NAMES = [
  "C1 0°",
  "C1 45°",
  "C1 90°",
  "C1 Random",
  "C2 0°",
  "C2 45°",
  "C2 90°",
  "C2 Random",
  "C3 0°",
  "C3 45°",
  "C3 90°",
  "C3 Random",
  "C4 0° TAB",
  "C4 45° TAB",
  "C4 90° TAB",
  "C4 Random TAB",
  "C4 0° MNT",
  "C4 45° MNT",
  "C4 90° MNT",
  "C4 Random MNT"
];

const OUTDOOR_EVENT_NAMES = [
  "C1 0°",
  "C1 45°",
  "C1 90° Short",
  "C1 90° Long",
  "C1 Random",
  "C2 0°",
  "C2 45°",
  "C2 90° Short",
  "C2 90° Long",
  "C2 Random",
  "C3 0°",
  "C3 45°",
  "C3 90° Short",
  "C3 90° Long",
  "C3 Random",
  "C4 0° TAB",
  "C4 45° TAB",
  "C4 90° Short TAB",
  "C4 90° Long TAB",
  "C4 Random TAB",

  "C4 0° MNT",
  "C4 45° MNT",
  "C4 90° Short MNT",
  "C4 90° Long MNT",
  "C4 Random MNT"
];

let selectedSetKey = null;
let selectedScenarioId = null;

let appData = {
  homes: []
};

let selectedHomeId = null;
let selectedParticipantId = null;

let startTime = null;
let endTime = null;
let stopwatchInterval = null;

let timerDurationSeconds = 30;


// =====================================================
// DOM ELEMENTS
// =====================================================

const dom = {
  // Pages
  homePage: document.getElementById("homePage"),
  homeDetailsPage: document.getElementById("homeDetailsPage"),
  trackerPage: document.getElementById("trackerPage"),

  // Lists
  homesList: document.getElementById("homesList"),
  participantsList: document.getElementById("participantsList"),
  logList: document.getElementById("logList"),

  // Text displays
  selectedHomeTitle: document.getElementById("selectedHomeTitle"),
  trackerTitle: document.getElementById("trackerTitle"),
  // scenarioText: document.getElementById("scenarioText"),
  // startTimeText: document.getElementById("startTime"),
  // endTimeText: document.getElementById("endTime"),
  // stopwatchDisplay: document.getElementById("stopwatchDisplay"),

  // Inputs
  newHomeInput: document.getElementById("newHomeInput"),
  newParticipantInput: document.getElementById("newParticipantInput"),
  // bufferBeforeInput: document.getElementById("bufferBeforeInput"),
  // bufferAfterInput: document.getElementById("bufferAfterInput"),

  // Buttons
  addHomeBtn: document.getElementById("addHomeBtn"),
  addParticipantBtn: document.getElementById("addParticipantBtn"),
  startBtn: document.getElementById("startBtn"),
  stopBtn: document.getElementById("stopBtn"),
  saveBtn: document.getElementById("saveBtn"),
  backToHomesBtn: document.getElementById("backToHomesBtn"),
  backToHomeDetailsBtn: document.getElementById("backToHomeDetailsBtn"),
  setButtons: document.getElementById("setButtons"),
  eventChecklist: document.getElementById("eventChecklist"),

  exportHomeCsvBtn: document.getElementById("exportHomeCsvBtn"),
};


// =====================================================
// LOCAL STORAGE
// =====================================================

function saveData() {
  localStorage.setItem("scenarioTrackerData", JSON.stringify(appData));
}

function loadData() {
  const saved = localStorage.getItem("scenarioTrackerData");

  if (saved) {
    appData = JSON.parse(saved);
  }
}


// =====================================================
// HELPER FUNCTIONS
// =====================================================

function makeId() {
  return Date.now().toString();
}

function formatScenarioNumber(num) {
  return String(num).padStart(3, "0");
}

function createEventList(eventNames) {
  return eventNames.map((name, index) => {
    return {
      id: index + 1,
      name: name,
      status: "not_started",
      log: null
    };
  });
}

function formatTime(date) {
  return date.toLocaleString();
}

function addSeconds(date, seconds) {
  return new Date(date.getTime() + seconds * 1000);
}

function getDurationSeconds(start, end) {
  return Math.round((end - start) / 1000);
}

function resetTimerDisplay() {
  startTime = null;
  endTime = null;

  clearInterval(stopwatchInterval);

  if (dom.startTimeText) {
    dom.startTimeText.textContent = "Not Complete";
  }

  if (dom.endTimeText) {
    dom.endTimeText.textContent = "Not stopped";
  }

  if (dom.stopwatchDisplay) {
    dom.stopwatchDisplay.textContent = "30.000";
  }
}

function formatCountdown(ms) {
  const totalMs = Math.max(ms, 0);
  const secs = Math.floor(totalMs / 1000);
  const millis = totalMs % 1000;

  return String(secs).padStart(2, "0") + "." + String(millis).padStart(3, "0");
}


// =====================================================
// SELECTED DATA HELPERS
// =====================================================

function getSelectedHome() {
  return appData.homes.find(home => home.id === selectedHomeId);
}

function getSelectedParticipant() {
  const home = getSelectedHome();
  return home.participants.find(participant => participant.id === selectedParticipantId);
}


// =====================================================
// PAGE NAVIGATION
// =====================================================

function showPage(page) {
  dom.homePage.classList.add("hidden");
  dom.homeDetailsPage.classList.add("hidden");
  dom.trackerPage.classList.add("hidden");

  page.classList.remove("hidden");
}

function openHome(homeId) {
  selectedHomeId = homeId;
  renderParticipants();
  showPage(dom.homeDetailsPage);
}

function openTracker(participantId) {
  selectedParticipantId = participantId;
  selectedSetKey = "indoorDay";
  selectedScenarioId = 1;

  resetTimerDisplay();
  renderTracker();
  showPage(dom.trackerPage);
}

function openEvent(eventId) {
  selectedScenarioId = eventId;
  resetTimerDisplay();
  renderTracker();

  setTimeout(() => {
    const currentEvent = document.querySelector(".current-event");
    if (currentEvent) {
      currentEvent.scrollIntoView({
        behavior: "smooth",
        block: "center"
      });
    }
  }, 50);
}
// =====================================================
// RENDER HOMES
// =====================================================

function renderHomes() {
  dom.homesList.innerHTML = "";

  appData.homes.forEach(home => {
    const div = document.createElement("div");
    div.className = "home-item";

    div.innerHTML = `
      <strong>${home.name}</strong><br>
      Date: ${home.date || "No date set"}<br>
      Participants: ${home.participants.length}<br>

      <button onclick="openHome('${home.id}')">Open Home</button>
      <button onclick="editHome('${home.id}')">Edit Home</button>
      <button class="danger-btn" onclick="deleteHome('${home.id}')">Delete Home</button>
    `;

    dom.homesList.appendChild(div);
  });
}

// =====================================================
// RENDER PARTICIPANTS
// =====================================================

function renderParticipants() {
  const home = getSelectedHome();

  dom.selectedHomeTitle.textContent =
    `${home.name} ${home.date ? "- " + home.date : ""}`;

  dom.participantsList.innerHTML = "";

  home.participants.forEach(participant => {
    let completedCount = 0;

    Object.values(participant.sets).forEach(set => {
      set.events.forEach(event => {
        if (event.status === "completed") completedCount++;
      });
    });

    const div = document.createElement("div");
    div.className = "participant-item";

    div.innerHTML = `
      <strong>${participant.name}</strong><br>
      Completed Events: ${completedCount} / 90<br>
      
      <button onclick="openTracker('${participant.id}')">
        Start / Continue Tracking
      </button>
      <button onclick="editParticipant('${participant.id}')">
        Edit Participant
      </button>
      <button class="danger-btn" onclick="deleteParticipant('${participant.id}')">
        Delete Participant
      </button>
    `;

    dom.participantsList.appendChild(div);
  });
}

// =====================================================
// RENDER TRACKER PAGE
// =====================================================

function renderTracker() {
  const home = getSelectedHome();
  const participant = getSelectedParticipant();
  const selectedSet = participant.sets[selectedSetKey];
  const selectedEvent = selectedSet.events.find(event => event.id === selectedScenarioId);

  dom.trackerTitle.textContent =
  `${home.name}${home.date ? " - " + home.date : ""} / ${participant.name}`;

  renderSetButtons();
  renderEventChecklist();
  renderLogs();
}

function renderSetButtons() {
  const participant = getSelectedParticipant();

  dom.setButtons.innerHTML = "";

  Object.keys(participant.sets).forEach(setKey => {
    const set = participant.sets[setKey];

    const completedCount = set.events.filter(event => event.status === "completed").length;

    const button = document.createElement("button");
    button.textContent = `${set.label} (${completedCount}/${set.events.length})`;

    if (setKey === selectedSetKey) {
      button.classList.add("active-set");
    }

    button.onclick = () => {
      selectedSetKey = setKey;

      const firstIncomplete = set.events.find(event => event.status !== "completed");
      selectedScenarioId = firstIncomplete ? firstIncomplete.id : set.events[0].id;

      resetTimerDisplay();
      renderTracker();
    };

    dom.setButtons.appendChild(button);
  });
}

function renderEventChecklist() {
  const participant = getSelectedParticipant();
  const selectedSet = participant.sets[selectedSetKey];

  dom.eventChecklist.innerHTML = "";

  selectedSet.events.forEach(event => {
    const div = document.createElement("div");
    div.className = "event-row";

    if (event.status === "completed") {
      div.classList.add("completed-event");
    } else {
      div.classList.add("incomplete-event");
    }

    if (event.id === selectedScenarioId) {
      div.classList.add("current-event");
    }

    const statusText = event.status === "completed" ? "Completed" : "Not Complete";

    let timestampHtml = "";

    if (event.log) {
      timestampHtml = `
        <div class="timestamp-grid">
          <div>
            <strong>Actual Start</strong><br>
            ${event.log.start}
          </div>

          <div>
            <strong>Clip Start</strong><br>
            ${event.log.clipStart}
          </div>

          <div>
            <strong>Actual End</strong><br>
            ${event.log.end}
          </div>

          <div>
            <strong>Clip End</strong><br>
            ${event.log.clipEnd}
          </div>

          <div class="duration-row">
            <strong>Duration:</strong>
            ${event.log.durationSeconds} seconds
          </div>
        </div>

        <button onclick="deleteLog(${event.id})">Delete Timestamp</button>
      `;
    }

    let timerHtml = "";

    if (event.id === selectedScenarioId) {
      timerHtml = `
        <div class="inline-timer">
          <h2>${selectedSet.label} - ${event.name}</h2>

          <div id="inlineStopwatchDisplay">30.000</div>

          <div class="timer-settings-grid">
            <label>
              Buffer before:
              <input id="inlineBufferBeforeInput" type="number" value="1" min="0">
            </label>

            <label>
              Buffer after:
              <input id="inlineBufferAfterInput" type="number" value="1" min="0">
            </label>

            <label>
              Timer duration:
              <input id="inlineDurationInput" type="number" value="30" min="1">
            </label>
          </div>

          <div class="timer-action-row">
            <button id="inlineStartBtn" class="timer-main-btn start-main">START</button>
            <button id="inlineStopBtn" class="timer-main-btn stop-main">STOP</button>
          </div>

          <div class="timer-action-row">
            <button id="inlineResetBtn" class="timer-main-btn reset-main">RESET</button>
            <button id="inlineSaveBtn" class="timer-main-btn save-main">SAVE</button>
          </div>

          <p>Start: <span id="inlineStartTime">Not started</span></p>
          <p>End: <span id="inlineEndTime">Not stopped</span></p>
        </div>
      `;
    }

    div.innerHTML = `
      <div class="event-main">
        <strong>${event.name}</strong><br>
        <span>${statusText}</span>

        ${timestampHtml}

        <button onclick="openEvent(${event.id})">Open Timer</button>

        ${timerHtml}
      </div>
    `;

    dom.eventChecklist.appendChild(div);
  });

  reconnectTimerButtons();
}

function reconnectTimerButtons() {
  dom.stopwatchDisplay = document.getElementById("inlineStopwatchDisplay");
  dom.bufferBeforeInput = document.getElementById("inlineBufferBeforeInput");
  dom.bufferAfterInput = document.getElementById("inlineBufferAfterInput");
  dom.startTimeText = document.getElementById("inlineStartTime");
  dom.endTimeText = document.getElementById("inlineEndTime");

  const startBtn = document.getElementById("inlineStartBtn");
  const stopBtn = document.getElementById("inlineStopBtn");
  const saveBtn = document.getElementById("inlineSaveBtn");
  const resetBtn = document.getElementById("inlineResetBtn");

  if (startBtn) startBtn.addEventListener("click", startTimer);
  if (stopBtn) stopBtn.addEventListener("click", stopTimer);
  if (saveBtn) saveBtn.addEventListener("click", saveScenarioAndNext);
  if (resetBtn) resetBtn.addEventListener("click", resetCurrentTimer);
}



function renderLogs() {
  dom.logList.innerHTML = `
    Timestamps are now shown inside each event above.
  `;
}
// =====================================================
// HOME ACTIONS
// =====================================================

function addHome() {
  const name = dom.newHomeInput.value.trim();

  if (!name) {
    alert("Enter a home name.");
    return;
  }

  appData.homes.push({
    id: makeId(),
    name,
    date: new Date().toISOString().split("T")[0],
    participants: []
  });

  dom.newHomeInput.value = "";

  saveData();
  renderHomes();
}

function deleteHome(homeId) {
  const home = appData.homes.find(home => home.id === homeId);

  const confirmDelete = confirm(
    `Delete "${home.name}" and all participants/timestamps inside it?`
  );

  if (!confirmDelete) return;

  appData.homes = appData.homes.filter(home => home.id !== homeId);

  saveData();
  renderHomes();
}

function editHome(homeId) {
  const home = appData.homes.find(home => home.id === homeId);

  const newName = prompt("Edit home name:", home.name);
  if (newName === null) return;

  const cleanName = newName.trim();

  if (!cleanName) {
    alert("Home name cannot be empty.");
    return;
  }

  home.name = cleanName;

  saveData();
  renderHomes();
}

// =====================================================
// PARTICIPANT ACTIONS
// =====================================================

function addParticipant() {
  const name = dom.newParticipantInput.value.trim();
  const home = getSelectedHome();

  if (!name) {
    alert("Enter a participant name.");
    return;
  }

  home.participants.push({
    id: makeId(),
    name,

    sets: {
      indoorDay: {
        label: "Indoor Day",
        events: createEventList(INDOOR_EVENT_NAMES)
      },

      outdoorDay: {
        label: "Outdoor Day",
        events: createEventList(OUTDOOR_EVENT_NAMES)
      },

      indoorNight: {
        label: "Indoor Night",
        events: createEventList(INDOOR_EVENT_NAMES)
      },

      outdoorNight: {
        label: "Outdoor Night",
        events: createEventList(OUTDOOR_EVENT_NAMES)
      }
    }
  });

  dom.newParticipantInput.value = "";

  saveData();
  renderParticipants();
}

function deleteParticipant(participantId) {
  const home = getSelectedHome();
  const participant = home.participants.find(p => p.id === participantId);

  const confirmDelete = confirm(
    `Delete "${participant.name}" and all of their timestamps?`
  );

  if (!confirmDelete) return;

  home.participants = home.participants.filter(p => p.id !== participantId);

  saveData();
  renderParticipants();
}

function editParticipant(participantId) {
  const home = getSelectedHome();
  const participant = home.participants.find(p => p.id === participantId);

  const newName = prompt("Edit participant name:", participant.name);
  if (newName === null) return;

  const cleanName = newName.trim();
  if (!cleanName) {
    alert("Participant name cannot be empty.");
    return;
  }

  participant.name = cleanName;

  saveData();
  renderParticipants();
}

// =====================================================
// STOPWATCH / TIMER ACTIONS
// =====================================================

function updateStopwatch() {
  if (!startTime) {
    dom.stopwatchDisplay.textContent = formatCountdown(timerDurationSeconds * 1000);
    return;
  }

  const now = new Date();
  const elapsedMs = now - startTime;
  const totalMs = timerDurationSeconds * 1000;
  const remainingMs = Math.max(totalMs - elapsedMs, 0);

  dom.stopwatchDisplay.textContent = formatCountdown(remainingMs);

  if (remainingMs <= 0) {
    stopTimer();
  }
}

function startTimer() {
  if (startTime && !endTime) {
    alert("Timer is already running.");
    return;
  }

  if (startTime && endTime) {
    alert("Timer already stopped. Save it or open the event again to redo.");
    return;
  }

  timerDurationSeconds =
    Number(document.getElementById("inlineDurationInput").value) || 30;

  startTime = new Date();
  endTime = null;

  dom.startTimeText.textContent = formatTime(startTime);
  dom.endTimeText.textContent = "Not stopped";
  dom.stopwatchDisplay.textContent = formatCountdown(timerDurationSeconds * 1000);

  clearInterval(stopwatchInterval);
  stopwatchInterval = setInterval(updateStopwatch, 10);
}

function stopTimer() {
  if (!startTime) {
    alert("Press Start first.");
    return;
  }

  if (endTime) {
    alert("Timer is already stopped.");
    return;
  }

  endTime = new Date();
  dom.endTimeText.textContent = formatTime(endTime);

  clearInterval(stopwatchInterval);
  updateStopwatch();
}

function saveScenarioAndNext() {
  const participant = getSelectedParticipant();
  const selectedSet = participant.sets[selectedSetKey];
  const selectedEvent = selectedSet.events.find(event => event.id === selectedScenarioId);

  if (!startTime || !endTime) {
    alert("Press Start and Stop before saving.");
    return;
  }

  const bufferBefore = Number(dom.bufferBeforeInput.value) || 0;
  const bufferAfter = Number(dom.bufferAfterInput.value) || 0;

  const clipStart = addSeconds(startTime, -bufferBefore);
  const clipEnd = addSeconds(endTime, bufferAfter);

  selectedEvent.status = "completed";
  selectedEvent.log = {
    start: formatTime(startTime),
    end: formatTime(endTime),
    clipStart: formatTime(clipStart),
    clipEnd: formatTime(clipEnd),
    durationSeconds: getDurationSeconds(startTime, endTime),
    startISO: startTime.toISOString(),
    endISO: endTime.toISOString(),
    clipStartISO: clipStart.toISOString(),
    clipEndISO: clipEnd.toISOString(),
    status: "completed"
  };

  const nextIncomplete = selectedSet.events.find(event => event.status !== "completed");

  if (nextIncomplete) {
    selectedScenarioId = nextIncomplete.id;
  } else {
    selectedScenarioId = selectedEvent.id;
  }

  resetTimerDisplay();
  saveData();
  renderTracker();
}

function resetCurrentTimer() {
  clearInterval(stopwatchInterval);

  startTime = null;
  endTime = null;

  timerDurationSeconds =
    Number(document.getElementById("inlineDurationInput").value) || 30;

  dom.stopwatchDisplay.textContent = formatCountdown(timerDurationSeconds * 1000);
  dom.startTimeText.textContent = "Not started";
  dom.endTimeText.textContent = "Not stopped";
}

// =====================================================
// LOG ACTIONS
// =====================================================

function deleteLog(eventId) {
  const participant = getSelectedParticipant();
  const selectedSet = participant.sets[selectedSetKey];
  const event = selectedSet.events.find(event => event.id === eventId);

  const confirmDelete = confirm("Delete this timestamp?");
  if (!confirmDelete) return;

  event.status = "not_started";
  event.log = null;

  selectedScenarioId = eventId;

  saveData();
  renderTracker();
}


// =====================================================
// EVENT LISTENERS
// =====================================================

dom.addHomeBtn.addEventListener("click", addHome);
dom.addParticipantBtn.addEventListener("click", addParticipant);

dom.exportHomeCsvBtn.addEventListener("click", exportSelectedHomeCsv);

// dom.startBtn.addEventListener("click", startTimer);
// dom.stopBtn.addEventListener("click", stopTimer);
// dom.saveBtn.addEventListener("click", saveScenarioAndNext);

dom.backToHomesBtn.addEventListener("click", () => {
  renderHomes();
  showPage(dom.homePage);
});

dom.backToHomeDetailsBtn.addEventListener("click", () => {
  renderParticipants();
  showPage(dom.homeDetailsPage);
});

// =====================================================
// EXPORT 
// =====================================================

function exportSelectedHomeCsv() {
  const home = getSelectedHome();

  const rows = [[
    "House",
    "Date",
    "Participant",
    "Set",
    "Event",
    "Status",
    "Actual Start",
    "Actual End",
    "Clip Start",
    "Clip End",
    "Duration Seconds"
  ]];

  home.participants.forEach(participant => {
    Object.values(participant.sets).forEach(set => {
      set.events.forEach(event => {
        rows.push([
          home.name,
          home.date || "",
          participant.name,
          set.label,
          event.name,
          event.status,
          event.log ? event.log.start : "",
          event.log ? event.log.end : "",
          event.log ? event.log.clipStart : "",
          event.log ? event.log.clipEnd : "",
          event.log ? event.log.durationSeconds : ""
        ]);
      });
    });
  });

  const csvContent = rows
    .map(row => row.map(value => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\n");

  const blob = new Blob([csvContent], { type: "text/csv" });
  const url = URL.createObjectURL(blob);

  const safeHomeName = home.name.replace(/[^a-z0-9]/gi, "-").toLowerCase();
  const fileDate = home.date || new Date().toISOString().split("T")[0];

  const link = document.createElement("a");
  link.href = url;
  link.download = `${safeHomeName}-${fileDate}-scenario-log.csv`;
  link.click();

  URL.revokeObjectURL(url);
}

// =====================================================
// APP STARTUP
// =====================================================

loadData();
renderHomes();
showPage(dom.homePage);
