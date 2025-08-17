document.addEventListener("DOMContentLoaded", () => {
  const tournamentCards = document.querySelectorAll(".tournament-card");
  const actionsSection = document.getElementById("tournament-actions");
  const tournamentTitle = document.getElementById("tournament-title");

  tournamentCards.forEach(card => {
    card.addEventListener("click", () => {
      const name = card.dataset.tournament;
      tournamentTitle.textContent = name;
      actionsSection.classList.remove("hidden");
      window.scrollTo({ top: actionsSection.offsetTop, behavior: "smooth" });
    });
  });
});
