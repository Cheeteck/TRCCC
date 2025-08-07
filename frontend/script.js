const coin = document.getElementById('coin');
const flipButton = document.getElementById('flipButton');
const resultDiv = document.getElementById('result');
const balanceSpan = document.getElementById('balance');

async function updateBalance() {
  const res = await fetch('/balance');
  const data = await res.json();
  balanceSpan.innerText = data.balance.toLocaleString();
}

async function flipCoin() {
  const bet = parseInt(document.getElementById('betAmount').value);
  const choice = document.getElementById('choice').value;

  if (isNaN(bet) || bet <= 0) {
    resultDiv.textContent = '❌ Enter a valid bet amount!';
    return;
  }

  flipButton.disabled = true;
  resultDiv.textContent = '';

  // Start spinning animation
  coin.classList.add('spin');

  try {
    const res = await fetch('/coinflip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bet, choice, winChance: 0.499 }),
    });

    if (!res.ok) {
      const error = await res.json();
      resultDiv.textContent = `❌ Error: ${error.error}`;
      flipButton.disabled = false;
      coin.classList.remove('spin');
      return;
    }

    const data = await res.json();

    // Wait for animation to finish (2 seconds)
    setTimeout(() => {
      // Update coin face based on result
      if (data.flip_result === 'heads') {
        coin.textContent = '🪙'; // heads emoji or image
      } else {
        coin.textContent = '🪘'; // tails emoji or image
      }

      resultDiv.textContent = `🪙 It landed on ${data.flip_result.toUpperCase()}. You ${data.result.toUpperCase()}! New balance: ${data.new_balance.toLocaleString()}`;
      updateBalance();
      flipButton.disabled = false;
      coin.classList.remove('spin');
    }, 2000);

  } catch (error) {
    resultDiv.textContent = '❌ Error during flip.';
    flipButton.disabled = false;
    coin.classList.remove('spin');
  }
}

flipButton.addEventListener('click', flipCoin);
window.onload = updateBalance;
