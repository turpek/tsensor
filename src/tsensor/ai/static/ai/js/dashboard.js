document.addEventListener('DOMContentLoaded', function() {
    const sensorSections = document.querySelectorAll('.sensor-section');
    let sensorConfigs = Array.from(sensorSections).map(section => ({
        index: parseInt(section.dataset.sensorIndex),
        name: section.dataset.sensorName
    }));

    // Funções auxiliares para buscar URLs baseadas no prefixo do blueprint
    const getUrl = (path) => {
        // Assume que o blueprint está em /ai (se mudar no register_blueprint, muda aqui)
        return `/ai${path}`;
    };

    function initCharts() {
        sensorConfigs.forEach(config => {
            Plotly.newPlot(`chart-${config.index}`, [{
                x: [], y: [], type: 'scatter', mode: 'lines+markers', name: config.name
            }], { margin: { t: 10, r: 10, b: 40, l: 60 } });

            Plotly.newPlot(`hist-${config.index}`, [{
                x: [], type: 'histogram', marker: { color: '#6c757d' }
            }], { margin: { t: 10, r: 10, b: 40, l: 40 } });
        });
    }

    initCharts();

    function updateDashboard() {
        // Atualiza estatísticas e histograma
        fetch(getUrl('/api/stats'))
            .then(r => r.json())
            .then(stats => {
                if (stats.length === 0) return;
                if (stats.length !== sensorConfigs.length) {
                    location.reload(); return;
                }
                stats.forEach((stat, i) => {
                    document.getElementById(`min-${i}`).textContent = stat.min.toFixed(2);
                    document.getElementById(`max-${i}`).textContent = stat.max.toFixed(2);
                    document.getElementById(`mean-${i}`).textContent = stat.mean.toFixed(2);
                    document.getElementById(`std-${i}`).textContent = stat.std.toFixed(2);
                    
                    // restyle é MUITO mais rápido que update para histogramas
                    Plotly.restyle(`hist-${i}`, { x: [stat.residuals] });
                });
            }).catch(e => console.debug("Erro stats:", e));

        // Atualiza série temporal com limite de pontos para não travar o browser
        fetch(getUrl('/api/history'))
            .then(r => r.json())
            .then(data => {
                if (data.length === 0) return;
                
                // Limita a renderização aos últimos 300 pontos para manter a fluidez
                const visualData = data.length > 300 ? data.slice(-300) : data;
                const times = visualData.map(row => new Date(row[0] * 1000));

                sensorConfigs.forEach(config => {
                    const values = visualData.map(row => row[config.index + 1]);
                    Plotly.restyle(`chart-${config.index}`, { x: [times], y: [values] });
                });
            }).catch(e => console.debug("Erro history:", e));
    }

    setInterval(updateDashboard, 2000);
});
