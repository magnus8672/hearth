try { const theme = localStorage.getItem('hearth.theme'); if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme; } catch {}
