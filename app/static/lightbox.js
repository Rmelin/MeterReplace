document.addEventListener("DOMContentLoaded", () => {
  const overlay = document.createElement("div")
  overlay.className = "lightbox-overlay is-hidden"
  overlay.innerHTML = `
    <div class="lightbox-content">
      <button class="lightbox-close" type="button" aria-label="Luk">×</button>
      <img class="lightbox-image" alt="Forstørret foto" />
    </div>
  `
  document.body.appendChild(overlay)

  const lightboxImage = overlay.querySelector(".lightbox-image")
  const closeButton = overlay.querySelector(".lightbox-close")

  const close = () => {
    overlay.classList.add("is-hidden")
    lightboxImage.src = ""
    document.body.classList.remove("lightbox-open")
  }

  const open = (src, alt) => {
    if (!src) return
    lightboxImage.src = src
    lightboxImage.alt = alt || "Forstørret foto"
    overlay.classList.remove("is-hidden")
    document.body.classList.add("lightbox-open")
  }

  document.addEventListener("click", (event) => {
    const target = event.target.closest("img[data-lightbox]")
    if (!target) return
    open(target.src, target.alt)
  })

  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      close()
    }
  })

  closeButton.addEventListener("click", close)

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      close()
    }
  })
})
