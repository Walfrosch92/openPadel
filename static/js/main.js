// Theme Management
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    // Update button icon
    const themeBtn = document.querySelector('#themeToggle');
    if (themeBtn) {
        themeBtn.innerHTML = newTheme === 'dark' ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
    }
}

// Load saved theme
const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);

// Update current time
function updateCurrentTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('de-DE');
    const element = document.getElementById('currentTime');
    if (element) {
        element.textContent = timeString;
    }
}

setInterval(updateCurrentTime, 1000);
updateCurrentTime();

// Connection status monitoring
function updateConnectionStatus() {
    const element = document.getElementById('connectionStatus');
    if (element) {
        element.textContent = navigator.onLine ? 'Verbunden' : 'Offline';
        element.style.color = navigator.onLine ? 'var(--success)' : 'var(--danger)';
    }
}

window.addEventListener('online', updateConnectionStatus);
window.addEventListener('offline', updateConnectionStatus);
updateConnectionStatus();