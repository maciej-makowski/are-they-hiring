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

// Chart.js bar chart
function initChart() {
    const canvas = document.getElementById('postsChart');
    if (!canvas || typeof dailyCounts === 'undefined') return;

    const labels = dailyCounts.map(d => d.date);
    const data = dailyCounts.map(d => d.count);

    // Plugin: draw warning triangle for zero-count days
    const warningPlugin = {
        id: 'warningTriangle',
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            const meta = chart.getDatasetMeta(0);
            meta.data.forEach((bar, i) => {
                if (data[i] === 0) {
                    const x = bar.x;
                    const y = chart.scales.y.getPixelForValue(0) - 10;
                    ctx.save();
                    ctx.fillStyle = '#f59e0b';
                    ctx.font = '16px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.fillText('\u26A0', x, y);
                    ctx.restore();
                }
            });
        }
    };

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'SWE Postings',
                data: data,
                backgroundColor: data.map(v => v > 0 ? 'rgba(34, 197, 94, 0.7)' : 'rgba(239, 68, 68, 0.3)'),
                borderColor: data.map(v => v > 0 ? '#22c55e' : '#ef4444'),
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            onClick(e, elements) {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    window.location.href = '/day/' + labels[idx];
                }
            },
            scales: {
                x: {
                    ticks: { color: '#888', maxRotation: 45 },
                    grid: { color: '#222' }
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: '#888' },
                    grid: { color: '#222' }
                }
            },
            plugins: {
                legend: { labels: { color: '#ccc' } }
            }
        },
        plugins: [warningPlugin]
    });
}

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
    initChart();
    if (document.querySelector('.hero-yes') && typeof confetti === 'function') {
        confetti({ particleCount: 100, spread: 60, origin: { y: 0.6 } });
    }
});
