# ViveMedellín - CSS Design System

## Archivos

| Archivo | Propósito |
|---------|-----------|
| `variables.css` | Variables CSS globales (colores, espaciados, etc.) |
| `style.css` | Estilos base del sitio |
| `components.css` | Componentes reutilizables |

## Uso de Variables

### Colores Principales

```css
/* En lugar de: */
.mi-elemento {
  background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
  color: #11998e;
}

/* Usar: */
.mi-elemento {
  background: var(--gradient-primary);
  color: var(--color-primary);
}
```

### Colores con Transparencia

```css
/* En lugar de: */
.overlay {
  background: rgba(17, 153, 142, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.12);
}

/* Usar: */
.overlay {
  background: var(--primary-30);
  border: 1px solid var(--white-12);
}
```

### Espaciado

```css
/* En lugar de: */
.card {
  padding: 1.5rem;
  margin-bottom: 2rem;
}

/* Usar: */
.card {
  padding: var(--space-6);
  margin-bottom: var(--space-8);
}
```

### Bordes y Radios

```css
/* En lugar de: */
.button {
  border-radius: 9999px;
}

.card {
  border-radius: 24px;
}

/* Usar: */
.button {
  border-radius: var(--radius-full);
}

.card {
  border-radius: var(--radius-3xl);
}
```

### Sombras

```css
/* En lugar de: */
.card {
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
}

.button:hover {
  box-shadow: 0 6px 20px rgba(17, 153, 142, 0.4);
}

/* Usar: */
.card {
  box-shadow: var(--shadow-2xl);
}

.button:hover {
  box-shadow: var(--shadow-primary-md);
}
```

### Transiciones

```css
/* En lugar de: */
.element {
  transition: all 0.3s ease;
}

/* Usar: */
.element {
  transition: var(--transition-all);
}
```

## Variables Disponibles

### Colores
- `--color-primary` / `--color-primary-light` / `--color-primary-dark`
- `--color-accent` / `--color-accent-light` / `--color-accent-dark`
- `--color-success`, `--color-warning`, `--color-danger`, `--color-purple`
- `--color-gray-50` hasta `--color-gray-900`

### Gradientes
- `--gradient-primary` - Botones y CTAs
- `--gradient-primary-hover` - Estado hover
- `--gradient-dark-bg` - Fondo de secciones
- `--gradient-warning` - Ratings
- `--gradient-purple` - Elementos exclusivos

### Opacidades
- `--white-5` hasta `--white-90`
- `--black-20` hasta `--black-70`
- `--primary-5` hasta `--primary-60`
- `--accent-5` hasta `--accent-40`
- `--dark-card-70`, `--dark-card-95`

### Espaciado
- `--space-1` (4px) hasta `--space-20` (80px)

### Radios
- `--radius-sm` (6px) hasta `--radius-4xl` (28px)
- `--radius-full` (9999px)

### Sombras
- `--shadow-sm` hasta `--shadow-3xl`
- `--shadow-primary-sm/md/lg`
- `--shadow-accent-sm/md`

### Z-Index
- `--z-dropdown` (100)
- `--z-modal` (500)
- etc.

## Clases de Utilidad

```html
<!-- Texto con gradiente -->
<h1 class="text-gradient">Título con gradiente</h1>

<!-- Efecto glassmorphism -->
<div class="glass">Contenido glass oscuro</div>
<div class="glass-light">Contenido glass claro</div>

<!-- Hover lift effect -->
<div class="hover-lift">Se eleva al hover</div>

<!-- Glow effects -->
<div class="glow-primary">Brillo primario</div>
<div class="glow-accent">Brillo acento</div>
```

