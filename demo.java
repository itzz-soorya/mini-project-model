class Solution
{
    static void Main(string[] args)
    {
        NotesStore store = new NotesStore();
        int n = int.Parse(Console.ReadLine());

        for (int i = 0; i < n; i++)
        {
            string[] operationInfo = Console.ReadLine().Split(' ');
            
            if (operationInfo[0] == "AddNote")
            {
                string state = operationInfo[1];
                string name = operationInfo.Length > 2 ? operationInfo[2] : "";
                
                try
                {
                    store.AddNote(state, name);
                }
                catch
                {
                    // Ignore exceptions for AddNote
                }
            }
            else if (operationInfo[0] == "GetNotes")
            {
                List<string> result = store.GetNotes(operationInfo[1]);
                
                if (result.Count == 0)
                    Console.WriteLine("No Notes");
                else
                    Console.WriteLine(string.Join(",", result));
            }
        }
    }
}
