try do
  import_file "~/.iex.exs"
rescue
  _ -> :ok
end

alias Diplomat.{Key, Entity, Property, Value, PropertyList, Client, Query}
