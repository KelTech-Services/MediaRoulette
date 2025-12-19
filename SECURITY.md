# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in PlexRoulette, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### Preferred Methods

1. **GitHub Private Vulnerability Reporting** (recommended)  
   Use the "Report a vulnerability" button in the [Security tab](https://github.com/KelTech-Services/PlexRoulette/security/advisories/new)

2. **Email**  
   Send details to: dev_security@keltech.services

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes (optional)

### What to Expect

- Acknowledgment within 48 hours
- Status updates as we investigate
- Credit in the release notes (unless you prefer anonymity)

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | ✅ Yes             |

## Security Best Practices for Users

- Always set a strong, unique `SECRET_KEY` environment variable
- Use HTTPS when exposing PlexRoulette outside your local network
- Keep your Docker images updated to the latest version
