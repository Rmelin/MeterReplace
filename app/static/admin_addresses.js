document.addEventListener('DOMContentLoaded', () => {
  const panels = document.querySelectorAll('[data-panel]')
  const buttons = document.querySelectorAll('[data-toggle-panel]')

  const hidePanel = (panel) => {
    panel.classList.add('is-hidden')
  }

  const showPanel = (panel) => {
    panel.classList.remove('is-hidden')
  }

  const togglePanel = (target) => {
    panels.forEach((panel) => {
      if (panel.getAttribute('data-panel') === target) {
        const isHidden = panel.classList.contains('is-hidden')
        if (isHidden) {
          showPanel(panel)
        } else {
          hidePanel(panel)
        }
      } else {
        hidePanel(panel)
      }
    })
  }

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      const target = button.getAttribute('data-toggle-panel')
      if (!target) return
      togglePanel(target)
    })
  })
})
