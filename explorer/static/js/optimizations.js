// Lazy Loading de Imágenes
document.addEventListener('DOMContentLoaded', function() {
    // Configurar Intersection Observer para lazy loading
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                
                // Cargar la imagen
                if (img.dataset.src) {
                    img.src = img.dataset.src;
                    img.classList.add('loaded');
                }
                
                // Cargar srcset si existe
                if (img.dataset.srcset) {
                    img.srcset = img.dataset.srcset;
                }
                
                // Dejar de observar esta imagen
                observer.unobserve(img);
            }
        });
    }, {
        rootMargin: '50px 0px', // Cargar 50px antes de que entre en viewport
        threshold: 0.01
    });

    // Observar todas las imágenes con lazy loading
    const lazyImages = document.querySelectorAll('img[data-src]');
    lazyImages.forEach(img => imageObserver.observe(img));
    
    // Precargar imágenes críticas (hero, primera vista)
    const criticalImages = document.querySelectorAll('[data-critical]');
    criticalImages.forEach(img => {
        if (img.dataset.src) {
            img.src = img.dataset.src;
        }
    });
});

// Optimización de scroll
let ticking = false;
function requestTick() {
    if (!ticking) {
        window.requestAnimationFrame(updateNavbar);
        ticking = true;
    }
}

function updateNavbar() {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar?.classList.add('scrolled');
    } else {
        navbar?.classList.remove('scrolled');
    }
    ticking = false;
}

// Debounce para eventos de scroll
let scrollTimer;
window.addEventListener('scroll', () => {
    if (scrollTimer) {
        clearTimeout(scrollTimer);
    }
    scrollTimer = setTimeout(requestTick, 10);
});

// Precarga de rutas al hacer hover
document.addEventListener('DOMContentLoaded', function() {
    const links = document.querySelectorAll('a[href^="/"]');
    const preloadedUrls = new Set();
    
    links.forEach(link => {
        link.addEventListener('mouseenter', function() {
            const url = this.href;
            if (!preloadedUrls.has(url)) {
                const linkEl = document.createElement('link');
                linkEl.rel = 'prefetch';
                linkEl.href = url;
                document.head.appendChild(linkEl);
                preloadedUrls.add(url);
            }
        });
    });
});

// Comprimir y optimizar localStorage
const CompressedStorage = {
    set: function(key, value) {
        try {
            const compressed = LZString.compressToUTF16(JSON.stringify(value));
            localStorage.setItem(key, compressed);
        } catch (e) {
            console.error('Error saving to localStorage:', e);
        }
    },
    get: function(key) {
        try {
            const compressed = localStorage.getItem(key);
            if (!compressed) return null;
            return JSON.parse(LZString.decompressFromUTF16(compressed));
        } catch (e) {
            console.error('Error reading from localStorage:', e);
            return null;
        }
    }
};

// Web Vitals - Medir rendimiento
if ('PerformanceObserver' in window) {
    // Largest Contentful Paint
    new PerformanceObserver((entryList) => {
        const entries = entryList.getEntries();
        const lastEntry = entries[entries.length - 1];
        console.log('LCP:', lastEntry.renderTime || lastEntry.loadTime);
    }).observe({entryTypes: ['largest-contentful-paint']});
    
    // First Input Delay
    new PerformanceObserver((entryList) => {
        const firstInput = entryList.getEntries()[0];
        const fid = firstInput.processingStart - firstInput.startTime;
        console.log('FID:', fid);
    }).observe({entryTypes: ['first-input']});
    
    // Cumulative Layout Shift
    let cls = 0;
    new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries()) {
            if (!entry.hadRecentInput) {
                cls += entry.value;
                console.log('CLS:', cls);
            }
        }
    }).observe({entryTypes: ['layout-shift']});
} 