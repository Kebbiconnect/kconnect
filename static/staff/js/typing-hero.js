/** Dashboard welcome animation. Text only; never renders messages as HTML. */
class TypingHero {
    constructor(element) {
        this.element = element;
        this.messages = (element.dataset.messages || '').split('|').filter(Boolean);
        this.typingSpeed = parseInt(element.dataset.speed, 10) || 100;
        this.deletingSpeed = parseInt(element.dataset.deleteSpeed, 10) || 50;
        this.pauseDuration = parseInt(element.dataset.pause, 10) || 2000;
        this.messageIndex = 0;
        this.charIndex = 0;
        this.isDeleting = false;
        if (this.messages.length) {
            this.type();
        }
    }

    type() {
        if (!this.element.isConnected) return;
        const message = this.messages[this.messageIndex];
        this.charIndex += this.isDeleting ? -1 : 1;
        this.element.textContent = message.substring(0, this.charIndex);
        let delay = this.isDeleting ? this.deletingSpeed : this.typingSpeed;
        if (!this.isDeleting && this.charIndex === message.length) {
            this.isDeleting = true;
            delay = this.pauseDuration;
        } else if (this.isDeleting && this.charIndex === 0) {
            this.isDeleting = false;
            this.messageIndex = (this.messageIndex + 1) % this.messages.length;
            delay = this.typingSpeed;
        }
        window.setTimeout(() => this.type(), delay);
    }
}

function initializeTypingHeroes() {
    const reduceMotion = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelectorAll('.typing-text').forEach(element => {
        if (element.dataset.typingInitialized === 'true') return;
        element.dataset.typingInitialized = 'true';
        if (reduceMotion) {
            element.textContent = (element.dataset.messages || '').split('|')[0] ||
                element.textContent;
            return;
        }
        new TypingHero(element);
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeTypingHeroes);
} else {
    initializeTypingHeroes();
}
