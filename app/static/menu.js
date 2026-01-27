document.addEventListener('DOMContentLoaded', () => {
  const toggles = document.querySelectorAll('[data-nav-toggle]')
  const storageKey = 'adminNavSection'

  const setOpen = (section) => {
    toggles.forEach((toggle) => {
      const targetId = toggle.getAttribute('data-nav-toggle')
      const sectionEl = document.querySelector(`[data-nav-section="${targetId}"]`)
      const isActive = section && targetId === section
      toggle.setAttribute('aria-expanded', String(isActive))
      if (sectionEl) {
        sectionEl.classList.toggle('is-hidden', !isActive)
      }
    })
    if (section) {
      localStorage.setItem(storageKey, section)
    } else {
      localStorage.removeItem(storageKey)
    }
  }

  const initial = localStorage.getItem(storageKey)
  if (initial) {
    setOpen(initial)
  }

  toggles.forEach((toggle) => {
    toggle.addEventListener('click', () => {
      const targetId = toggle.getAttribute('data-nav-toggle')
      if (!targetId) return
      const isOpen = toggle.getAttribute('aria-expanded') === 'true'
      setOpen(isOpen ? '' : targetId)
    })
  })
})
