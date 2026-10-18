/** Every refresh supersedes earlier results, including failures and session changes. */
export class LatestRequestGate {
  private generation = 0;
  invalidate() { this.generation += 1; }
  begin() {
    const generation = ++this.generation;
    return { isCurrent: () => generation === this.generation };
  }
}
