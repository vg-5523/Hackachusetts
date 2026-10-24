function App() {
  return (
    <div className="flex h-screen flex-col bg-slate-50 text-slate-900">
      <main className="flex flex-1 items-center justify-center overflow-hidden">
        <h1 className="text-2xl font-semibold">Ambulance Scribe</h1>
      </main>
      <footer className="shrink-0 border-t border-slate-200 bg-white px-4 py-2 text-center text-sm text-slate-600">
        decision support, not clinical advice.
      </footer>
    </div>
  );
}

export default App;
