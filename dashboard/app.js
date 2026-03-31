/**
 * Sentinel Dashboard — Client-Side Application
 * 
 * In production this would connect via WebSocket to the running agent.
 * For the hackathon demo, it runs the agent via API endpoint and updates the UI.
 */

class SentinelDashboard {
    constructor() {
        this.equityHistory = [10000];
        this.iteration = 0;
        this.lastData = null;
        this.init();
    }

    init() {
        this.drawEquityChart();
        this.updateTimestamp();
        this.startSimulatedUpdates();
    }

    /**
     * Update the dashboard with new data from the agent
     */
    update(data) {
        this.lastData = data;
        this.iteration = data.iteration || this.iteration + 1;

        // Update iteration counter
        document.getElementById('iteration-count').textContent = `Iteration #${this.iteration}`;

        // Update equity
        if (data.risk_metrics) {
            const rm = data.risk_metrics;
            this.updateEquity(rm);
            this.updateRiskGuardrails(rm);
        }

        // Update signals
        if (data.signals && data.signals.length > 0) {
            this.updateSignals(data.signals);
            this.updateRegime(data.signals[0]);
        }

        // Update trades
        if (data.trades && data.trades.length > 0) {
            this.addTrades(data.trades);
        }

        this.updateTimestamp();
    }

    updateEquity(rm) {
        const equityEl = document.getElementById('equity-amount');
        const equity = rm.equity || 10000;
        
        equityEl.textContent = this.formatNumber(equity);
        this.equityHistory.push(equity);
        if (this.equityHistory.length > 50) this.equityHistory.shift();

        // Color based on P&L
        const startEquity = this.equityHistory[0];
        equityEl.style.color = equity >= startEquity ? '#10b981' : '#f43f5e';

        document.getElementById('peak-equity').textContent = '$' + this.formatNumber(rm.peak_equity || equity);
        document.getElementById('drawdown').textContent = ((rm.drawdown || 0) * 100).toFixed(1) + '%';
        
        const dailyPnl = rm.daily_pnl || 0;
        const dailyEl = document.getElementById('daily-pnl');
        dailyEl.textContent = (dailyPnl >= 0 ? '+' : '') + '$' + this.formatNumber(Math.abs(dailyPnl));
        dailyEl.style.color = dailyPnl >= 0 ? '#10b981' : '#f43f5e';

        // Risk status
        const statusEl = document.getElementById('risk-status');
        const status = rm.status || 'normal';
        statusEl.textContent = status.toUpperCase();
        statusEl.style.background = status === 'normal' 
            ? 'rgba(16, 185, 129, 0.12)' 
            : status === 'caution' 
            ? 'rgba(245, 158, 11, 0.12)' 
            : 'rgba(244, 63, 94, 0.12)';
        statusEl.style.color = status === 'normal' 
            ? '#10b981' 
            : status === 'caution' 
            ? '#f59e0b' 
            : '#f43f5e';

        this.drawEquityChart();
    }

    updateRegime(signal) {
        const regime = signal.regime || 'sideways';
        const confidence = signal.confidence || 0;
        const strategy = signal.strategy || 'mean_reversion';

        // Regime indicator
        const regimeLabel = document.getElementById('regime-label');
        regimeLabel.textContent = regime.toUpperCase().replace('_', ' ');

        const ring = document.querySelector('.regime-ring');
        
        if (regime === 'trending_up') {
            ring.style.borderColor = '#10b981';
            ring.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.2)';
            ring.innerHTML = '';
            ring.style.setProperty('--regime-icon', '"↗"');
            regimeLabel.style.color = '#10b981';
        } else if (regime === 'trending_down') {
            ring.style.borderColor = '#f43f5e';
            ring.style.boxShadow = '0 0 20px rgba(244, 63, 94, 0.2)';
            regimeLabel.style.color = '#f43f5e';
        } else {
            ring.style.borderColor = '#06b6d4';
            ring.style.boxShadow = '0 0 20px rgba(6, 182, 212, 0.15)';
            regimeLabel.style.color = '#06b6d4';
        }

        // ADX
        const adxMatch = signal.reasoning?.match(/ADX=(\d+\.?\d*)/);
        if (adxMatch) {
            const adx = parseFloat(adxMatch[1]);
            document.getElementById('adx-value').textContent = adx.toFixed(1);
            document.getElementById('adx-bar').style.width = Math.min(adx / 50 * 100, 100) + '%';
        }

        // Confidence
        const confMatch = signal.reasoning?.match(/conf=(\d+\.?\d*)/);
        if (confMatch) {
            const conf = parseFloat(confMatch[1]) * 100;
            document.getElementById('confidence-value').textContent = conf.toFixed(0) + '%';
            document.getElementById('confidence-bar').style.width = conf + '%';
        }

        // Strategy
        const strategyEl = document.getElementById('active-strategy');
        const strategyNames = {
            'mean_reversion': 'Mean Reversion',
            'momentum': 'Momentum',
        };
        strategyEl.textContent = strategyNames[strategy] || strategy;
    }

    updateSignals(signals) {
        const list = document.getElementById('signals-list');
        list.innerHTML = '';

        signals.forEach(sig => {
            const actionClass = sig.signal === 'buy' ? 'signal-buy' 
                             : sig.signal === 'sell' ? 'signal-sell' 
                             : 'signal-hold';

            const shortReasoning = sig.reasoning 
                ? sig.reasoning.replace(/\[Regime:.*?\]\s*/, '').substring(0, 80) 
                : '';

            const item = document.createElement('div');
            item.className = 'signal-item';
            item.innerHTML = `
                <div class="signal-header">
                    <span class="signal-symbol">${sig.symbol}</span>
                    <span class="signal-action ${actionClass}">${sig.signal.toUpperCase()}</span>
                </div>
                <div class="signal-body">
                    <span class="signal-price">$${this.formatNumber(sig.price)}</span>
                    <span class="signal-strategy">${sig.strategy === 'mean_reversion' ? 'Mean Reversion' : 'Momentum'}</span>
                </div>
                <div class="signal-reasoning">${shortReasoning}</div>
            `;
            list.appendChild(item);
        });
    }

    updateRiskGuardrails(rm) {
        const ddPct = ((rm.drawdown || 0) * 100);
        document.getElementById('dd-guardrail').textContent = `${ddPct.toFixed(1)}% / 10%`;
        const ddBar = document.getElementById('dd-bar');
        ddBar.style.width = (ddPct / 10 * 100) + '%';
        ddBar.className = `progress-fill ${ddPct > 7 ? 'guardrail-danger' : ddPct > 4 ? 'guardrail-warn' : 'guardrail-ok'}`;

        const dailyLossPct = rm.daily_pnl < 0 ? Math.abs(rm.daily_pnl) / rm.equity * 100 : 0;
        document.getElementById('daily-guardrail').textContent = `${dailyLossPct.toFixed(1)}% / 3%`;
        const dailyBar = document.getElementById('daily-bar');
        dailyBar.style.width = (dailyLossPct / 3 * 100) + '%';

        document.getElementById('positions-guardrail').textContent = `${rm.open_positions || 0} / 5`;
        document.getElementById('positions-bar').style.width = ((rm.open_positions || 0) / 5 * 100) + '%';
    }

    addTrades(trades) {
        const table = document.getElementById('trades-table');
        
        // Clear empty state if first trade
        if (table.querySelector('.trade-empty')) {
            table.innerHTML = `
                <div class="trade-row trade-row-header">
                    <span>Symbol</span><span>Side</span><span>Entry</span><span>Exit</span>
                    <span>Size</span><span>P&L</span><span>Strategy</span><span>Reason</span>
                </div>
            `;
        }

        trades.forEach(trade => {
            const row = document.createElement('div');
            row.className = 'trade-row';
            const pnl = trade.pnl || 0;
            row.innerHTML = `
                <span>${trade.symbol}</span>
                <span style="color:${trade.action === 'buy' ? '#10b981' : '#f43f5e'}">${trade.action?.toUpperCase()}</span>
                <span>$${this.formatNumber(trade.price)}</span>
                <span>—</span>
                <span>${trade.size?.toFixed(6)}</span>
                <span style="color:${pnl >= 0 ? '#10b981' : '#f43f5e'}">${pnl >= 0 ? '+' : ''}$${this.formatNumber(Math.abs(pnl))}</span>
                <span>${trade.strategy}</span>
                <span>Signal</span>
            `;
            table.appendChild(row);
        });

        document.getElementById('trade-stats').textContent = 
            `${table.querySelectorAll('.trade-row:not(.trade-row-header)').length} trades`;
    }

    drawEquityChart() {
        const canvas = document.getElementById('equity-chart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        
        canvas.width = canvas.offsetWidth * dpr;
        canvas.height = 120 * dpr;
        ctx.scale(dpr, dpr);

        const w = canvas.offsetWidth;
        const h = 120;
        const data = this.equityHistory;
        
        if (data.length < 2) {
            // Draw flat line
            ctx.strokeStyle = '#6366f1';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(0, h / 2);
            ctx.lineTo(w, h / 2);
            ctx.stroke();
            return;
        }

        const min = Math.min(...data) * 0.999;
        const max = Math.max(...data) * 1.001;
        const range = max - min || 1;

        // Gradient fill
        const gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, 'rgba(99, 102, 241, 0.15)');
        gradient.addColorStop(1, 'rgba(99, 102, 241, 0)');

        ctx.clearRect(0, 0, w, h);

        // Fill area
        ctx.beginPath();
        ctx.moveTo(0, h);
        data.forEach((v, i) => {
            const x = (i / (data.length - 1)) * w;
            const y = h - ((v - min) / range) * (h - 10) - 5;
            if (i === 0) ctx.lineTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.lineTo(w, h);
        ctx.closePath();
        ctx.fillStyle = gradient;
        ctx.fill();

        // Line
        ctx.beginPath();
        data.forEach((v, i) => {
            const x = (i / (data.length - 1)) * w;
            const y = h - ((v - min) / range) * (h - 10) - 5;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.stroke();

        // End dot
        const lastX = w;
        const lastY = h - ((data[data.length - 1] - min) / range) * (h - 10) - 5;
        ctx.beginPath();
        ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#6366f1';
        ctx.fill();
        ctx.beginPath();
        ctx.arc(lastX, lastY, 7, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(99, 102, 241, 0.3)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    updateTimestamp() {
        const now = new Date();
        document.getElementById('last-update').textContent = 
            `Last update: ${now.toLocaleTimeString()}`;
    }

    formatNumber(n) {
        return Number(n).toLocaleString('en-US', { 
            minimumFractionDigits: 2, 
            maximumFractionDigits: 2 
        });
    }

    /**
     * Simulated updates for demo purposes.
     * Replace with WebSocket/SSE in production.
     */
    startSimulatedUpdates() {
        // Initial demo data matching real agent output
        this.update({
            iteration: 1,
            signals: [
                {
                    symbol: "BTCUSD",
                    regime: "sideways",
                    signal: "hold",
                    confidence: 0.0,
                    strategy: "mean_reversion",
                    price: 67450.40,
                    reasoning: "[Regime: sideways (conf=0.58, ADX=16.3)] No mean reversion signal. RSI=57.2, %B=0.68"
                },
                {
                    symbol: "ETHUSD",
                    regime: "sideways",
                    signal: "hold",
                    confidence: 0.0,
                    strategy: "mean_reversion",
                    price: 2063.96,
                    reasoning: "[Regime: sideways (conf=0.61, ADX=15.8)] No mean reversion signal. RSI=57.8, %B=0.66"
                }
            ],
            trades: [],
            risk_metrics: {
                equity: 10000.00,
                peak_equity: 10000.00,
                drawdown: 0.0,
                daily_pnl: 0.0,
                open_positions: 0,
                status: "normal"
            }
        });
    }
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new SentinelDashboard();
});
