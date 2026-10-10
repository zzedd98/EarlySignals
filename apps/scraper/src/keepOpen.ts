import readline from 'readline';

/** Pause interactive pour laisser le temps de lire les logs (workers / erreurs). */
export async function pauseBeforeExit(): Promise<void> {
  if (process.env.SCRAPER_KEEP_OPEN === 'false') {
    return;
  }

  console.log('\n⏸️  Terminé — appuyez sur Entrée pour fermer ce terminal...');

  await new Promise<void>((resolve) => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });
    rl.question('', () => {
      rl.close();
      resolve();
    });
  });
}
