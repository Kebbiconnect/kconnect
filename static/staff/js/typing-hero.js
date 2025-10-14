/**
 * Typing Hero - Reusable Typing Animation Component
 * Automatically initializes all elements with class "typing-text"
 */

class TypingHero {
    constructor(element) {
        this.element = element;
        this.messages = element.dataset.messages ? element.dataset.messages.split('|') : [];
        this.typingSpeed = parseInt(element.dataset.speed) || 100;
        this.deletingSpeed = parseInt(element.dataset.deleteSpeed) || 50;
        this.pauseDuration = parseInt(element.dataset.pause) || 2000;
        
        this.messageIndex = 0;
        this.charIndex = 0;
        this.isDeleting = false;
        
        if (this.messages.length > 0) {
            this.type();
        }
    }
    
    type() {
        const currentMessage = this.messages[this.messageIndex];
        
        if (this.isDeleting) {
            this.element.textContent = currentMessage.substring(0, this.charIndex - 1);
            this.charIndex--;
        } else {
            this.element.textContent = currentMessage.substring(0, this.charIndex + 1);
            this.charIndex++;
        }
        
        if (!this.isDeleting && this.charIndex === currentMessage.length) {
            setTimeout(() => { this.isDeleting = true; }, this.pauseDuration);
        } else if (this.isDeleting && this.charIndex === 0) {
            this.isDeleting = false;
            this.messageIndex = (this.messageIndex + 1) % this.messages.length;
        }
        
        setTimeout(() => this.type(), this.isDeleting ? this.deletingSpeed : this.typingSpeed);
    }
}

// Auto-initialize all typing elements when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const typingElements = document.querySelectorAll('.typing-text');
    typingElements.forEach(element => {
        setTimeout(() => {
            new TypingHero(element);
        }, 500);
    });
});
