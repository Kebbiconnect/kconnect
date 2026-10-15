module.exports = {
    darkMode: "class",
    content: [
        "./templates/**/*.html",
        "./{core,staff,campaigns,events,donations,media,telegram_integration}/templates/**/*.html",
        "./{core,staff,leadership,campaigns,events,donations,media,rest_api,telegram_integration}/**/*.py",
        "./static/staff/js/**/*.js"
    ],
    theme: {
        extend: {
            colors: {
                "kpn-green": "#28a745",
                "kpn-action": "#176b36",
                "kpn-blue": "#0066cc",
                "kpn-dark": "#1a1a1a",
                "kpn-gray": "#f4f4f4"
            }
        }
    },
    plugins: []
};