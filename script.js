(() => {
  const cards = Array.from(document.querySelectorAll('.parameter-card'));
  const filterButtons = Array.from(document.querySelectorAll('.filter-btn'));
  const activeGif = document.getElementById('activeGif');
  const activeTitle = document.getElementById('activeTitle');
  const activeDescription = document.getElementById('activeDescription');
  const activeGroup = document.getElementById('activeGroup');

  const groupNames = {
    physical: 'Physical', chemical: 'Chemical', biological: 'Biological', optical: 'Optical / Solids'
  };

  cards.forEach(card => {
    card.addEventListener('click', () => {
      cards.forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      activeGif.src = card.dataset.src;
      activeTitle.textContent = card.dataset.title;
      activeDescription.textContent = card.dataset.description;
      activeGroup.textContent = groupNames[card.dataset.group] || 'Environmental Parameter';
      document.querySelector('.viewer').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  filterButtons.forEach(button => {
    button.addEventListener('click', () => {
      filterButtons.forEach(b => b.classList.remove('active'));
      button.classList.add('active');
      const filter = button.dataset.filter;
      cards.forEach(card => {
        card.classList.toggle('hidden', filter !== 'all' && card.dataset.group !== filter);
      });
    });
  });

  const slides = Array.from(document.querySelectorAll('.showcase-card'));
  const dotsWrap = document.querySelector('.carousel-dots');
  const prev = document.querySelector('.carousel-arrow.left');
  const next = document.querySelector('.carousel-arrow.right');
  let slideIndex = 0;

  const dots = slides.map((_, i) => {
    const dot = document.createElement('button');
    dot.type = 'button';
    dot.setAttribute('aria-label', `Show preview ${i + 1}`);
    dot.addEventListener('click', () => showSlide(i));
    dotsWrap.appendChild(dot);
    return dot;
  });

  function showSlide(index) {
    slideIndex = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => slide.classList.toggle('active', i === slideIndex));
    dots.forEach((dot, i) => dot.classList.toggle('active', i === slideIndex));
  }

  prev.addEventListener('click', () => showSlide(slideIndex - 1));
  next.addEventListener('click', () => showSlide(slideIndex + 1));
  showSlide(0);
})();
