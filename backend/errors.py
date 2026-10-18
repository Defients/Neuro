from .security import redact

# Explanations based on the official Cortex error-code reference. No automatic quota retries.
ERRORS = {
    -32021: ('Invalid application credentials.', 'Replace the exposed secret, then enter the matching Client ID and NEW secret locally.', False),
    -32022: ('The license device activation limit was reached.', 'Ask EMOTIV support for an activation transfer or entitlement change. A developer license does not bypass this limit.', False),
    -32027: ('This application cannot use the requested license.', 'Use automatic license selection, or verify the app is entitled to the selected developer license.', False),
    -32019: ('No local session quota is available.', 'Review the verified license. Explicitly allocate one session only if permitted; do not repeat activation attempts.', False),
    -32016: ('This stream is unavailable, unsupported, or unauthorized.', 'Check the returned license scopes, headset model, and session activation. Use only approved streams.', False),
    -32102: ('The application has not been approved.', 'Approve NeuralSignalStudio in EMOTIV Launcher, then run diagnostics again.', True),
    -32232: ('Professional EEG registration requires an entitlement this account lacks.', 'For MN8, review the app registration. If Professional EEG was unnecessarily enabled, register a replacement app with that option disabled.', False),
    -32012: ('The stream requires an activated session.', 'Review EEG entitlement and explicitly activate a session once.', False),
    -32014: ('The Cortex token is invalid.', 'Run authorization again after confirming the logged-in account.', True),
    -32015: ('The Cortex token has expired.', 'Run authorization again with the correct logged-in account.', True),
    -32024: ('The license has expired.', 'Renew or correct the entitlement with EMOTIV.', False),
    -32029: ('The offline license hard limit has been reached.', 'Connect to the internet and authorize again.', True),
    -32230: ('This headset is not supported by this license.', 'Contact EMOTIV to confirm MN8 stream entitlements.', False),
    -32225: ('Cortex forced an account logout.', 'Sign in again in EMOTIV Launcher.', True),
    -32602: ('Cortex rejected the request parameters.', 'Export the redacted diagnostic report and review the API integration.', False),
}


class CortexError(Exception):
    def __init__(self, code, message, operation):
        self.code, self.message, self.operation = code, redact(message), operation
        super().__init__(f'{operation}: {code}: {self.message}')

    def report(self):
        explanation, action, retry = ERRORS.get(self.code, ('Cortex could not complete this operation.', 'Inspect the sanitized original error and the official Cortex documentation.', False))
        return {'code': self.code, 'message': self.message, 'operation': self.operation, 'explanation': explanation, 'action': action, 'retry': retry, 'alternative': 'Synthetic demo and saved recordings remain available. LSL requires a separately verified stream.'}
