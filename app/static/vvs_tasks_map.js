const STATUS_COLORS = {
  planned: '#f59e0b',
  informed: '#38bdf8',
  completed: '#22c55e',
  closed: '#16a34a',
  not_home: '#ef4444',
  needs_reschedule: '#f97316',
  unplanned: '#64748b',
}

const MAP_DEFAULT = [56.2639, 9.5018]
const MAP_ZOOM = 7
const MAP_CENTER_ZOOM = 13

const searchInput = document.getElementById('map-search')
const statusButtons = Array.from(
  document.querySelectorAll('.map-filter-button')
)
const dateInput = document.getElementById('map-date')
const mapContainer = document.getElementById('vvs-task-map')

if (!mapContainer) {
  // Map is only shown when a date is selected.
} else {
  const map = L.map('vvs-task-map').setView(MAP_DEFAULT, MAP_ZOOM)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map)

  const markerLayer = L.featureGroup().addTo(map)
  let addresses = []
  let activeStatus = 'all'

  const applyFilterSwatches = () => {
    statusButtons.forEach((button) => {
      const status = button.dataset.status
      let color = ''
      if (status && status !== 'all') {
        color = STATUS_COLORS[status] || STATUS_COLORS.unplanned
      }
      if (color) {
        button.style.setProperty('--status-color', color)
      }
    })
  }

  const normalizeStatus = (status) => (status || '').trim().toLowerCase()
  const statusColor = (status) =>
    STATUS_COLORS[normalizeStatus(status)] || STATUS_COLORS.unplanned

  const updateMarkers = () => {
    markerLayer.clearLayers()
    addresses
      .filter((row) => row.latitude !== null && row.longitude !== null)
      .forEach((row) => {
        const statusLabel = row.status_label || row.status
        const marker = L.circleMarker([row.latitude, row.longitude], {
          radius: 7,
          color: statusColor(row.status),
          weight: 2,
          fillColor: statusColor(row.status),
          fillOpacity: 0.8,
        })
        const timeLabel = row.starts_at && row.ends_at
          ? `${row.starts_at} – ${row.ends_at}`
          : ''
        marker.bindPopup(
          `<strong>${row.street} ${row.house_no}</strong><br>${row.zip} ${row.city}<br>${statusLabel}` +
            (timeLabel ? `<br>${timeLabel}` : '') +
            `<br><div class="map-popup-actions">
              <a class="ghost-button map-popup-button" href="/vvs/tasks/${row.appointment_id}/edit">Åben opgave</a>
            </div>`
        )
        markerLayer.addLayer(marker)
      })
  }

  const fitMapToVisible = () => {
    const bounds = markerLayer.getBounds()
    if (bounds && bounds.isValid()) {
      map.invalidateSize()
      window.requestAnimationFrame(() => {
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 })
      })
      return
    }
    map.setView(MAP_DEFAULT, MAP_CENTER_ZOOM)
  }

  const loadMapData = async () => {
    if (!dateInput || !dateInput.value) {
      addresses = []
      updateMarkers()
      fitMapToVisible()
      return
    }
    const params = new URLSearchParams()
    params.set('date', dateInput.value)
    if (searchInput && searchInput.value.trim()) {
      params.set('q', searchInput.value.trim())
    }
    if (activeStatus !== 'all') {
      params.set('status', activeStatus)
    }
    const response = await fetch(`/vvs/tasks/map-data?${params.toString()}`)
    const data = await response.json()
    addresses = data.addresses || []
    updateMarkers()
    fitMapToVisible()
  }

  let searchTimer = null
  const triggerSearch = () => {
    if (searchTimer) {
      clearTimeout(searchTimer)
    }
    searchTimer = setTimeout(loadMapData, 300)
  }

  if (searchInput) {
    searchInput.addEventListener('input', triggerSearch)
  }
  statusButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const status = button.dataset.status
      activeStatus = status || 'all'
      statusButtons.forEach((node) => node.classList.remove('is-active'))
      button.classList.add('is-active')
      loadMapData()
    })
  })

  applyFilterSwatches()
  loadMapData()
}
