// Epoch: Dario Amodei's claim date
const EPOCH = new Date('2025-03-14T00:00:00');

// Update counter every minute
function updateCounter() {
    const el = document.getElementById('counter-text');
    if (!el) return;
    const now = new Date();
    const diffMs = now - EPOCH;
    const totalDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const months = Math.floor(totalDays / 30);
    const daysR = totalDays % 30;
    el.textContent = `${months} month${months !== 1 ? 's' : ''}, ${daysR} day${daysR !== 1 ? 's' : ''}`;
}
setInterval(updateCounter, 60000);

// Sound + effects
function playCelebrate() {
    try {
        const audio = new Audio('/static/sounds/victory.mp3');
        audio.play().catch(() => {});
    } catch (e) {}
    if (typeof confetti === 'function') {
        confetti({ particleCount: 150, spread: 70, origin: { y: 0.6 } });
    }
}

function playAlarm() {
    try {
        const audio = new Audio('/static/sounds/alarm.mp3');
        audio.play().catch(() => {});
    } catch (e) {}
}

// Auto-confetti on YES state
document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('.hero-yes') && typeof confetti === 'function') {
        confetti({ particleCount: 100, spread: 60, origin: { y: 0.6 } });
    }
});
