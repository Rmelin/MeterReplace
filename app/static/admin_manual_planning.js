document.addEventListener('DOMContentLoaded', () => {
  const filterInput = document.querySelector('[data-address-filter]')
  const addressSelect = document.querySelector('[data-address-select]')
  const addressOptions = document.querySelectorAll('[data-address-option]')

  const applyFilter = () => {
    if (!filterInput) return
    const query = filterInput.value.trim().toLowerCase()
    addressOptions.forEach((option) => {
      const haystack = (option.getAttribute('data-address-search') || '').toLowerCase()
      const matches = !query || haystack.includes(query)
      option.hidden = !matches
      option.disabled = !matches
    })
    const listItems = document.querySelectorAll('[data-address-search]')
    listItems.forEach((item) => {
      const haystack = (item.getAttribute('data-address-search') || '').toLowerCase()
      const matches = !query || haystack.includes(query)
      item.style.display = matches ? '' : 'none'
    })
    if (addressSelect && addressSelect.selectedOptions.length) {
      const selected = addressSelect.selectedOptions[0]
      if (selected.hidden) {
        addressSelect.value = ''
      }
    }
  }

  if (filterInput) {
    filterInput.addEventListener('input', applyFilter)
  }
})
