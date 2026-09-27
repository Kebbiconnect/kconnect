/**
 * KPN Admin — AI Provider Connection Test
 * 
 * Triggered by the "Test" button in the AIProviderConfig list view.
 * Makes a secure fetch to the backend test endpoint.
 * API keys are NEVER handled in this script — all credential handling is server-side.
 */
function kpnTestProvider(providerId) {
    var btn = event.target;
    var originalText = btn.textContent;
    btn.textContent = 'Testing…';
    btn.disabled = true;
    btn.style.opacity = '0.7';

    var url = '/admin/telegram_integration/aiproviderconfig/test-provider/' + providerId + '/';

    fetch(url, {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';

        if (data.success) {
            alert('✅ Connection successful!\n\nProvider: ' + (data.provider_name || '') + '\nModel: ' + (data.model || '') + '\nResponse: ' + (data.response_preview || ''));
        } else {
            alert('❌ Connection failed\n\n' + (data.error || 'Unknown error') + (data.hint ? '\n\nHint: ' + data.hint : ''));
        }
    })
    .catch(function(err) {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
        alert('❌ Request failed: ' + err.message);
    });
}
